"""Dispatcher plan (decisions §9): deterministic, no model judgement, no network in `plan()`.

    dispatch.py --account <name> --state <file> --accounts-file <accounts.yaml> --private-trace <trace.csv>
                                                          gather from GitHub, then print the plan as JSON
    dispatch.py --account <name> --inputs <file.json>     print the plan from already gathered inputs
    dispatch.py --sync-trace --engine-trace f --private-trace f   open the trace sync PR

`plan(inputs)` is a pure function of the inputs (see tests/orch_helpers.world for the shape). The dispatcher
session then acts on the plan, in this order: claims (comment, then label), re-read comments and drop any claim
that lost (`dispatch.py` run again prints `withdraw`), then everything else.

Pace gates anything that spends quota: new starts, resumes, nudges and fresh replacements. Archiving, releasing,
labelling and the status comment never wait. Hotfixes ignore warnings, never a refusal.
"""
import argparse
import json
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import buildstatus  # noqa: E402
import gather  # noqa: E402
import pace  # noqa: E402

SILENT = timedelta(minutes=45)
RELEASE_AFTER = timedelta(hours=6)
STUCK_LIMIT = 3
PROTOTYPE_CAP = 3
PRIVATE_SOURCE = "stockpilot-hq/stockpilot"
PRIVATE_RUN_PROMPT = "docs/spec/v3/private-run.md"
ENGINE_TRACE = "checks/trace.csv"


# ---- paths -------------------------------------------------------------------------------------------------------

def _base(pattern):
    parts = []
    for seg in pattern.strip().rstrip("/").split("/"):
        if any(ch in seg for ch in "*?["):
            break
        parts.append(seg)
    return "/".join(parts)


def _shared(pattern):
    b = _base(pattern)
    return b == "contract" or b.startswith("contract/")


def overlap(a, b):
    if _shared(a) or _shared(b):
        return False
    x, y = _base(a), _base(b)
    return x == y or x.startswith(y + "/") or y.startswith(x + "/") or x == "" or y == ""


def paths_overlap(owns_a, owns_b):
    return any(overlap(a, b) for a in owns_a for b in owns_b)


def inside(path, owns):
    return any(_base(path) == _base(o) or _base(path).startswith(_base(o) + "/") for o in owns if not _shared(o))


# ---- helpers -----------------------------------------------------------------------------------------------------

def _winner(t):
    cl = sorted(t["claims"], key=lambda c: (pace.parse_time(c["at"]), c["session"]))
    return cl[0] if cl else None


def _has(t, label):
    return label in t["labels"]


def _resume_message(t, why):
    parts = [f"You stopped before ticket #{t['number']} was done ({why}). Continue on lane/{t['key']}."]
    if t["unticked"]:
        parts.append("Unticked checks: " + ", ".join(t["unticked"]) + ".")
    pr = t.get("pr") or {}
    if pr.get("ci") == "red" and pr.get("failing_output"):
        parts.append("Failing output of your PR's gate:\n" + pr["failing_output"])
    parts.append("Subscribe to your PR's events if you have not, fix what is red, and finish the whole ticket.")
    return "\n".join(parts)


def _start(t, reason, account):
    return {"ticket": t["key"], "number": t["number"], "account": account, "reason": reason,
            "branch": f"lane/{t['key']}", "model": "sonnet", "permission_mode": "auto",
            "source": PRIVATE_SOURCE, "environment": "Default", "prompt": f"Build issue #{t['number']}",
            "subscribe_own_pr": True}


# ---- the plan ----------------------------------------------------------------------------------------------------

def plan(inp):
    now = pace.parse_time(inp["now"])
    me = inp["account"]
    accounts = {a["name"]: a for a in inp["accounts"]}
    states = {}
    for name, a in accounts.items():
        states[name] = pace.account_state(inp["quota"].get(name, []), role=a["role"], mode=inp["mode"], now=now,
                                          weekly_reset=a["weekly_reset"], lapses=a.get("lapses"))
    mine = states[me]
    i_am_driver = accounts[me]["role"] == "driver"
    tickets = inp["tickets"]
    by_number = {t["number"]: t for t in tickets}
    out = {k: [] for k in ("claims", "withdraw", "release", "start", "resume", "nudge", "replace", "needs_planner",
                           "archive", "close", "private_runs", "new_tickets", "warnings")}
    out.update({"account": me, "sync_trace": None, "pace": mine})
    skipped = []

    live = [s for s in inp["sessions"] if s["account"] == me and s["kind"] == "builder" and s["status"] != "archived"]
    live_by_ticket = {}
    for s in live:
        live_by_ticket.setdefault(s["ticket"], []).append(s)

    # withdraw losing claims, release stale claims of refused accounts
    for t in tickets:
        w = _winner(t)
        if w and any(c["account"] == me for c in t["claims"]) and w["account"] != me:
            out["withdraw"].append({"ticket": t["key"], "number": t["number"], "account": me,
                                    "session": next(c["session"] for c in t["claims"] if c["account"] == me)})
        if w:
            st = states.get(w["account"])
            last_push = pace.parse_time((t.get("pr") or {}).get("last_push_at") or w["at"])
            if st and st["refused"] and now - last_push >= RELEASE_AFTER and not _merged(t):
                out["release"].append({"ticket": t["key"], "number": t["number"], "account": w["account"],
                                       "session": w["session"], "reason": "no push for 6 hours while refused"})

    def mine_won(t):
        w = _winner(t)
        return bool(w and w["account"] == me)

    starts_left = mine["max_starts"]

    def may_start(hotfix=False):
        nonlocal starts_left
        if hotfix:
            return not mine["refused"]
        return mine["can_start"] and (starts_left is None or starts_left > 0)

    def spend(hotfix=False):
        nonlocal starts_left
        if not hotfix and starts_left is not None:
            starts_left -= 1

    waiting = [t for t in tickets if _has(t, "prototype-waiting")]
    ui_ok = pace.ui_budget_ok(inp["cloudflare"]) and len(waiting) < PROTOTYPE_CAP

    # heartbeat: archive, nudge, resume, replace
    stuck_notes = []
    released = {(r["ticket"]) for r in out["release"]}
    for t in tickets:
        if not mine_won(t) or t["key"] in released:
            continue
        for s in live_by_ticket.get(t["key"], []):
            if _has(t, "prototype-waiting"):
                continue
            if _merged(t):
                out["archive"].append({"session": s["id"], "ticket": t["key"], "reason": "PR merged"})
                continue
            pr_red = (t.get("pr") or {}).get("ci") == "red"
            last = pace.parse_time(s["last_event_at"])
            reason = None
            if s["status"] == "failed":
                reason = "failed"
            elif s["status"] == "working" and s["connection"] == "disconnected":
                reason = "disconnected"
            elif s["status"] == "working" and now - last >= SILENT:
                reason = "silent"
            elif s["status"] == "idle" and (t["unticked"] or pr_red):
                reason = "idle"
            if not reason:
                continue
            nudged = s.get("nudged_at") and last <= pace.parse_time(s["nudged_at"])
            if nudged:
                count = t["stuck_count"] + 1
                out["replace"].append({"session": s["id"], "ticket": t["key"], "number": t["number"],
                                       "interrupt": True, "archive": True, "stuck_count": count})
                stuck_notes.append({"key": t["key"], "session": s["id"],
                                    "action": "interrupted and archived" + (", needs-planner" if count >= STUCK_LIMIT
                                                                            else ", fresh builder on lane/" + t["key"])})
                if count >= STUCK_LIMIT:
                    out["needs_planner"].append({"ticket": t["key"], "number": t["number"]})
                elif may_start() and (not t["ui"] or ui_ok):
                    out["start"].append(_start(t, "replacement", me))
                    spend()
                continue
            if not mine["can_start"]:
                skipped.append({"ticket": t["key"], "why": f"{reason} but pace says wait"})
                continue
            if reason == "idle":
                out["resume"].append({"session": s["id"], "ticket": t["key"], "number": t["number"], "reason": reason,
                                      "message": _resume_message(t, "idle with work left"),
                                      "unticked": t["unticked"], "subscribe_own_pr": True})
            else:
                out["nudge"].append({"session": s["id"], "ticket": t["key"], "number": t["number"], "reason": reason,
                                     "message": _resume_message(t, reason), "unticked": t["unticked"],
                                     "subscribe_own_pr": True})
            stuck_notes.append({"key": t["key"], "session": s["id"], "action": f"{reason}: " +
                                ("resumed" if reason == "idle" else "nudged")})

    # orphans: claimed by me, no live builder, nothing planned yet
    planned = {s["ticket"] for s in out["start"]}
    for t in tickets:
        if not mine_won(t) or t["key"] in planned or t["key"] in released or _merged(t):
            continue
        if live_by_ticket.get(t["key"]) or _has(t, "needs-planner") or t["stuck_count"] >= STUCK_LIMIT:
            continue
        if _has(t, "prototype-waiting"):
            skipped.append({"ticket": t["key"], "why": "prototype waiting without a session"})
            continue
        hot = _has(t, "hotfix")
        if may_start(hot) and (hot or not t["ui"] or ui_ok):
            out["start"].append(_start(t, "hotfix" if hot else "orphan", me))
            spend(hot)

    # claims
    held = []                       # owned paths of tickets running or claimed in this plan
    bare_running = False
    for t in tickets:
        if _winner(t) is not None and not _merged(t) and t["key"] not in released:
            held.append(t["owns"])
            bare_running = bare_running or not t["owns"]
    ready = []
    for t in tickets:
        if t["claims"] or t["vm"] or _has(t, "v3-vm") or _has(t, "needs-planner") or _has(t, "prototype-waiting"):
            continue
        if any(b in by_number for b in t["blocked_by"]):
            continue
        if t["ui"] and not i_am_driver:
            continue
        ready.append(t)
    unblocks = {t["number"]: sum(1 for u in tickets if t["number"] in u["blocked_by"]) for t in tickets}
    ready.sort(key=lambda t: (not _has(t, "hotfix"), not t["owns"], not t.get("critical"), -unblocks[t["number"]],
                              t["number"]))
    claimed_any = False
    for t in ready:
        hot = _has(t, "hotfix")
        if not may_start(hot):
            continue
        if t["ui"] and not ui_ok:
            continue
        if not hot:
            if bare_running or claimed_any and not t["owns"]:
                continue
            if not t["owns"] and held:
                continue
            if any(paths_overlap(t["owns"], h) for h in held):
                continue
        out["claims"].append({"ticket": t["key"], "number": t["number"], "account": me,
                              "comment": f"Claimed by {me}: <session id>", "label": f"pool:{me}"})
        out["start"].append(_start(t, "hotfix" if hot else "new_claim", me))
        spend(hot)
        claimed_any = True
        if not hot:
            held.append(t["owns"])
            bare_running = bare_running or not t["owns"]

    # left over lines
    known = set(inp.get("known_left_over", []))
    owns_by_key = {t["key"]: t["owns"] for t in tickets}
    for lo in inp.get("left_over", []):
        line = lo["line"]
        if line.strip().lower() == "none":
            continue
        files = lo.get("files", [])
        owns = owns_by_key.get(lo["ticket"], [])
        if files and all(inside(f, owns) for f in files):
            out["warnings"].append({"ticket": lo["ticket"], "line": line,
                                    "why": "Left over inside the ticket's own paths: finish it in the ticket"})
            continue
        lid = gather.left_over_id(lo["ticket"], line)
        if lid in known:
            continue
        out["new_tickets"].append({"id": lid, "from": lo["ticket"], "title": line[:100], "labels": ["ready-for-agent"],
                                   "body": f"Left over from {lo['ticket']}.\n\n{line}\n\nFiles: "
                                           + (", ".join(f"`{f}`" for f in files) or "not named")
                                           + f"\n\n<!-- left-over:{lid} -->"})

    # private runs
    live_private = {s.get("check") for s in inp["sessions"] if s["kind"] == "private-run" and s["status"] != "archived"}
    for r in inp.get("private_runs", []):
        if (pace.parse_time(r["due_at"]) <= now and not r.get("claimed_by") and r["check"] not in live_private
                and mine["can_start"]):
            out["private_runs"].append({"check": r["check"], "ticket": r["ticket"], "environment": "private",
                                        "prompt_file": PRIVATE_RUN_PROMPT, "model": "sonnet",
                                        "permission_mode": "auto", "account": me})

    # trace sync
    tr = inp.get("trace")
    if tr and _norm(tr["engine"]) != _norm(tr["private"]) and not tr.get("open_pr"):
        out["sync_trace"] = {"branch": "lane/trace-sync", "reason": "engine copy differs"}

    # close finished tickets: merged, nothing left to tick, no VM step
    out["close"] = [{"ticket": t["key"], "number": t["number"],
                     "action": f"close issue #{t['number']} in stockpilot-hq/stockpilot with the comment 'Merged. Closing.'"}
                    for t in tickets
                    if _merged(t) and not t["unticked"] and not t["vm"]]

    # status comment
    running = []
    for t in tickets:
        if mine_won(t) and not _merged(t):
            ss = live_by_ticket.get(t["key"], [])
            running.append({"key": t["key"], "number": t["number"], "session": ss[0]["id"] if ss else None,
                            "pr": (t.get("pr") or {}).get("number"),
                            "last_event_at": ss[0]["last_event_at"] if ss else None})
    mine_waiting = [t["key"] for t in waiting if mine_won(t)]
    for n in out["needs_planner"]:
        stuck_notes.append({"key": n["ticket"], "session": "-", "action": "needs-planner label added"})
    out["status_comment"] = {"account": me, "body": buildstatus.render(me, now, inp["quota"].get(me, []), running,
                                                                        mine_waiting, stuck_notes)}
    out["skipped"] = skipped
    return out


def _merged(t):
    return (t.get("pr") or {}).get("state") == "merged"


def _norm(text):
    return text.replace("\r\n", "\n").strip()


# ---- trace sync --------------------------------------------------------------------------------------------------

def sync_trace(engine_csv, private_csv, runner):
    """Open an engine PR that replaces checks/trace.csv with the private copy. `runner(verb, **kw)` does the REST calls."""
    if _norm(engine_csv) == _norm(private_csv):
        return None
    runner("branch", name="lane/trace-sync", base="main")
    runner("put_file", branch="lane/trace-sync", path=ENGINE_TRACE, content=private_csv,
           message="Sync checks/trace.csv from the private trace")
    return runner("open_pr", head="lane/trace-sync", base="main", title="Sync checks/trace.csv",
                  body="Refs stockpilot-hq/stockpilot#138\n\nThe engine's generated copy of the trace differs from the "
                       "private one; this replaces it.\n\nLeft over:\n- none\n")


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--account")
    ap.add_argument("--inputs", help="JSON file with the gathered inputs; - for stdin")
    ap.add_argument("--state", help="JSON file the dispatcher wrote (sessions, quota, cloudflare, private_runs, now); "
                                    "gathers the GitHub side itself")
    ap.add_argument("--accounts-file", help="the private ops/accounts.yaml")
    ap.add_argument("--private-trace", dest="private_trace")
    ap.add_argument("--sync-trace", action="store_true")
    ap.add_argument("--engine-trace", default=ENGINE_TRACE)
    a = ap.parse_args(argv)
    if a.sync_trace:
        import ghrunner
        res = sync_trace(Path(a.engine_trace).read_text(), Path(a.private_trace).read_text(), ghrunner.runner)
        print(json.dumps(res))
        return 0
    if a.state:
        import yaml
        cfg = yaml.safe_load(Path(a.accounts_file).read_text())
        engine = Path(ENGINE_TRACE)
        inp = gather.collect(a.account, json.load(open(a.state)), cfg["accounts"], cfg["mode"],
                             engine_trace=engine.read_text() if engine.exists() else "",
                             private_trace=Path(a.private_trace).read_text() if a.private_trace else "")
    elif a.account and a.inputs:
        inp = json.load(sys.stdin if a.inputs == "-" else open(a.inputs))
    else:
        ap.error("--account with --inputs or --state is required")
    inp["account"] = a.account
    print(json.dumps(plan(inp), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
