"""VM watcher (retro 2026-11-27): reads GitHub, decides when the orchestrator must wake, and why.

No model runs here. `decide()` is pure: tickets + saved state + time in, events + new state out.
The orchestrator session runs `watch.py wait --account <name>` in the background; it exits with the
first batch of events (or after two hours with a heartbeat), and the session acts on each line.
"""
from datetime import datetime, timedelta


def _t(s):
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _busy(tickets, account):
    """Slots in use. A merged ticket and one waiting for the owner's design approval hold no slot."""
    return sum(1 for x in tickets if x["claim"] and x["claim"]["account"] == account
               and not (x["pr"] and x["pr"]["state"] == "merged")
               and "prototype-waiting" not in x["labels"])


def _ready(x):
    return (not x["claim"] and not x["open_blockers"] and not x["pr"]
            and not {"needs-planner", "prototype-waiting"} & set(x["labels"]))


def _limited(state, account, now):
    until = state.get("limited_until", {}).get(account)
    return bool(until) and _t(until) > _t(now)


def _active(cfg, state, now):
    """Accounts that may start work now, in order: reserve accounts only once every other one is limited."""
    open_ = [a for a in cfg["accounts"] if not _limited(state, a["name"], now)]
    first = [a["name"] for a in open_ if not a.get("reserve")]
    return first or [a["name"] for a in open_]


def status(x):
    """The one `status:*` label a ticket carries, so any agent can list its siblings by state."""
    if "needs-planner" in x["labels"]:
        return "status:stuck"
    if "prototype-waiting" in x["labels"]:
        return "status:prototype"
    if x["pr"] and x["pr"]["state"] != "closed":
        return "status:pr"
    if x["claim"]:
        return "status:building"
    return "status:blocked" if x["open_blockers"] else "status:ready"


def decide(tickets, state, now, cfg, me, main=None):
    """Events for account `me`. Earlier accounts first; a reserve account takes work only when the others are limited."""
    events, new = [], {**state, "sent": dict(state.get("sent", {})),
                       "limited_until": dict(state.get("limited_until", {}))}
    until = new["limited_until"].get(me)
    if until and _t(until) <= _t(now):
        del new["limited_until"][me]
        events.append({"kind": "resume", "account": me})
    active = _active(cfg, state, now)
    free = {a["name"]: max(0, a["slots"] - _busy(tickets, a["name"])) if a["name"] in active else 0
            for a in cfg["accounts"]}
    if main and main.get("ci") == "red" and active and active[0] == me \
            and _once(new["sent"], f"main-red:{main['sha']}", now):
        events.append({"kind": "main-red", "account": me, "sha": main["sha"]})
    for x in sorted((x for x in tickets if _ready(x)), key=lambda x: x["number"]):
        taker = next((n for n in active if free[n] > 0 and (n == "primary" or not x["ui"])), None)   # UI runs on primary
        if taker:
            free[taker] -= 1
            if taker == me:
                events.append({"kind": "start", "account": me, "number": x["number"], "key": x["key"]})
    for x in sorted(tickets, key=lambda x: x["number"]):
        reply = x.get("owner_reply")
        mine = (x["claim"] or {}).get("account") == me or (not x["claim"] and active[:1] == [me])
        if reply and mine and "needs-owner" in x["labels"] and _once(new["sent"], f"reply:{reply[0]}", now):
            events.append({"kind": "owner-reply", "account": me, "number": x["number"], "key": x["key"], "text": reply[1]})
    for x in sorted((x for x in tickets if x["claim"] and x["claim"]["account"] == me), key=lambda x: x["number"]):
        events += _watch_builder(x, new["sent"], now, cfg)
    return events, new


def _latest(*stamps):
    got = [_t(s) for s in stamps if s]
    return max(got) if got else None


def _once(sent, key, now, every=None):
    """True the first time `key` is seen, and again `every` later when given."""
    last = sent.get(key)
    if last and (every is None or _t(now) - _t(last) < every):
        return False
    sent[key] = now
    return True


def _watch_builder(x, sent, now, cfg):
    me, sess, pr = x["claim"]["account"], x["claim"]["session"], x["pr"] or {}
    base = {"account": me, "number": x["number"], "key": x["key"]}
    if pr.get("state") == "merged":
        if _once(sent, f"done:{x['number']}", now):
            return [{"kind": "done", **base, "session": sess, "pr": pr["number"], "left_over": pr.get("left_over", [])}]
        return []
    if "prototype-waiting" in x["labels"]:
        return [{"kind": "prototype", **base, "session": sess}] if _once(sent, f"proto:{x['number']}", now) else []
    active = _latest(x["claim"]["at"], x["pushed_at"], pr.get("updated_at"))
    quiet = int((_t(now) - active).total_seconds() // 60)
    if pr.get("ci") == "red" and quiet >= 20 and _once(sent, f"red:{x['number']}:{pr['head_sha']}", now):
        return [{"kind": "check", "why": "red", **base, "session": sess, "minutes": quiet}]
    if x["ui"]:   # an owner-facing chat is never chased for being quiet
        return []
    if quiet >= cfg["quiet_minutes"] and _once(sent, f"quiet:{x['number']}", now,
                                                  timedelta(minutes=cfg["quiet_minutes"])):
        return [{"kind": "check", "why": "quiet", **base, "session": sess, "minutes": quiet}]
    return []


# ---- reading GitHub and transcripts ------------------------------------------------------------------------------
import json  # noqa: E402
import re  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
import time  # noqa: E402
from pathlib import Path  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import gather  # noqa: E402

ENGINE, PRIVATE = gather.ENGINE, gather.PRIVATE
BOARD_ISSUE = 195
SKIP = {133, BOARD_ISSUE}            # the spec and the build-status issue are not tickets
CLAIM = re.compile(r"Claimed by (\w+): (\S+)(?: \((lane/[\w-]+)\))?")


def to_ticket(issue, comments, open_numbers):
    body = issue.get("body") or ""
    labels = [l["name"] if isinstance(l, dict) else l for l in issue.get("labels", [])]
    gone = gather.withdrawn(comments)
    claims = [c for c in comments if CLAIM.match(c.get("body", ""))]
    live = [c for c in claims if CLAIM.match(c["body"]).groups()[:2] not in gone]
    claim = None
    if live:
        m = CLAIM.match(live[-1]["body"])
        claim = {"account": m.group(1), "session": m.group(2), "at": live[-1]["created_at"]}
        if m.group(3):
            claim["lane"] = m.group(3)
    ask, reply = None, None
    for c in comments:
        b = c.get("body", "")
        if b.startswith(ASK):
            ask, reply = b[len(ASK):].strip(), None
        elif ask and not b.startswith("🤖") and not CLAIM.match(b) and not re.match(r"(Withdrawn|Released) by", b):
            reply = (str(c.get("id", c["created_at"])), b.strip())
    blockers = gather.parse_blockers(body)
    return {"ask": ask, "owner_reply": reply, "number": issue["number"], "key": gather.parse_key(body) or f"LO{issue['number']}", "labels": labels,
            "blocked_by": blockers, "open_blockers": [b for b in blockers if b in open_numbers],
            "ui": "v3-ui" in labels, "claim": claim, "pr": None, "pushed_at": None}


ASK = "🤖 Needs you:"


def board(tickets, state, now):
    """The owner's one view of both accounts, written into the pinned build-status issue."""
    from zoneinfo import ZoneInfo
    ist = ZoneInfo("Asia/Kolkata")

    def link(x):
        c = x["claim"]
        return f" · [session](https://claude.ai/code/{c['session']}) ({c['account']})" if c else ""
    def pr(x):
        p = x["pr"]
        return f" · engine#{p['number']} {p['ci']}" if p else ""
    def ago_(x):
        last = _latest((x["claim"] or {}).get("at"), x["pushed_at"], (x["pr"] or {}).get("updated_at"))
        return f" · {int((_t(now) - last).total_seconds() // 60)} min since last activity" if last else ""
    needs = [x for x in tickets if {"needs-owner", "prototype-waiting", "needs-planner"} & set(x["labels"])]
    live = [x for x in tickets if x["claim"] and x not in needs and not (x["pr"] and x["pr"]["state"] == "merged")]
    out = [f"_Written by the VM watcher, {_t(now).astimezone(ist).strftime('%d %b %H:%M')} IST. "
           "Reply on a ticket's issue to answer it._", "", "## Needs you"]
    for x in needs:
        why = ("prototype ready to review in its builder chat" if "prototype-waiting" in x["labels"] else
               x.get("ask") or "stuck: a planning session must look at it")
        out.append(f"- **#{x['number']} {x['key']}**: {why}{link(x)}")
    out += ["- nothing" if not needs else "", "## Building"]
    out += [f"- #{x['number']} {x['key']}{pr(x)}{ago_(x)}{link(x)}" for x in live] or ["- nothing"]
    counts = {k: sum(1 for x in tickets if status(x) == k) for k in ("status:ready", "status:blocked")}
    lim = state.get("limited_until", {})
    out += ["", "## Queue", f"Ready: {counts['status:ready']} · Blocked: {counts['status:blocked']}", "",
            "## Accounts"]
    for a in CFG["accounts"]:
        until = lim.get(a["name"])
        role = "reserve" if a.get("reserve") else "works first"
        out.append(f"- {a['name']} ({role}): " + (f"at its limit until {_t(until).astimezone(ist).strftime('%H:%M IST')}" if until and
                                                    _t(until) > _t(now) else "available"))
    return "\n".join(out).replace("\n\n\n", "\n\n")


RESET = re.compile(r"resets (\d{1,2})(?::(\d\d))?\s*([ap]m)(?: \(([\w/]+)\))?", re.I)


def limit_from_transcripts(files, now):
    """The reset time of the newest usage-limit message in these transcripts, if it is still ahead of `now`."""
    from zoneinfo import ZoneInfo
    latest = None
    for f in files:
        for line in open(f):
            if '"rate_limit"' not in line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("error") != "rate_limit":
                continue
            text = " ".join(b.get("text", "") for b in d.get("message", {}).get("content", []) if isinstance(b, dict))
            m = RESET.search(text)
            if m and (latest is None or d["timestamp"] > latest[0]):
                latest = (d["timestamp"], m)
    if not latest:
        return None
    at, m = _t(latest[0]), latest[1]
    tz = ZoneInfo(m.group(4) or "Asia/Kolkata")
    hour = int(m.group(1)) % 12 + (12 if m.group(3).lower() == "pm" else 0)
    local = at.astimezone(tz)
    reset = local.replace(hour=hour, minute=int(m.group(2) or 0), second=0, microsecond=0)
    if reset <= local:
        reset += timedelta(days=1)
    return reset.isoformat() if reset > _t(now) else None


def context_tokens(path):
    last = 0
    for line in open(path):
        if '"usage"' not in line:
            continue
        try:
            u = json.loads(line)["message"]["usage"]
        except (ValueError, KeyError, TypeError):
            continue
        last = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get("cache_creation_input_tokens", 0)
    return last


def _api(path, *args):
    return gather.gh_api(path, *args)


def collect(api=_api, now=None):
    issues = [i for i in api(f"repos/{PRIVATE}/issues", "-f", "state=open", "-f", "per_page=100")
              if "pull_request" not in i]
    open_numbers = {i["number"] for i in issues}
    since = (datetime.fromisoformat(now) - timedelta(days=10)).isoformat() if now else "2026-11-20T00:00:00Z"
    comments = {}
    for c in api(f"repos/{PRIVATE}/issues/comments", "-f", f"since={since}", "-f", "per_page=100"):
        comments.setdefault(int(c["issue_url"].rsplit("/", 1)[1]), []).append(c)
    tickets = [to_ticket(i, sorted(comments.get(i["number"], []), key=lambda c: c["created_at"]), open_numbers)
               for i in issues if i["number"] not in SKIP and any(
                   (l["name"] if isinstance(l, dict) else l) == "ready-for-agent" for l in i["labels"])]
    prs = {p["head"]["ref"]: p for p in api(f"repos/{ENGINE}/pulls", "-f", "state=all", "-f", "sort=updated",
                                             "-f", "direction=desc", "-f", "per_page=100")}
    for x in tickets:
        lane = (x["claim"] or {}).get("lane") or f"lane/{x['key']}"
        p = prs.get(lane)
        if p:
            ci = "none"
            if p["state"] == "open":
                runs = api(f"repos/{ENGINE}/commits/{p['head']['sha']}/check-runs")
                ci = gather.check_state(runs.get("check_runs", []) if isinstance(runs, dict) else runs)
            x["pr"] = {"number": p["number"], "state": "merged" if p.get("merged_at") else p["state"], "ci": ci,
                       "head_sha": p["head"]["sha"], "updated_at": p["updated_at"],
                       "left_over": [lo["line"] for lo in gather.parse_left_over(p.get("body"))]}
        elif x["claim"]:
            try:
                c = api(f"repos/{ENGINE}/commits/{lane}")
                x["pushed_at"] = c["commit"]["committer"]["date"]
            except subprocess.CalledProcessError:
                pass   # no branch yet
    return tickets


# ---- command line ------------------------------------------------------------------------------------------------
STATE = Path.home() / ".local/state/stockpilot-watch/state.json"
ACCOUNTS = [{"name": "secondary", "slots": 3, "config_dir": "~/.claude-second"},
            {"name": "primary", "slots": 3, "config_dir": "~/.claude"}]   # both work at once, 2026-11-28
STATUS_LABELS = ["status:ready", "status:blocked", "status:building", "status:pr", "status:prototype", "status:stuck"]
CFG = {"accounts": ACCOUNTS, "quiet_minutes": 60}
HANDOFF_AT = 160_000   # every wake re-reads the context; a fresh one starts near 90k


def _load():
    try:
        return json.loads(STATE.read_text())
    except (OSError, ValueError):
        return {}


def _save(st):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE.with_suffix(".tmp")
    tmp.write_text(json.dumps(st, indent=1))
    tmp.replace(STATE)


def _now():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _my_transcript(account):
    conf = next(a for a in ACCOUNTS if a["name"] == account)["config_dir"]
    files = sorted(Path(conf).expanduser().glob("projects/*stockpilot*/*.jsonl"), key=lambda p: p.stat().st_mtime)
    for f in reversed(files[-15:]):
        with open(f) as fh:
            head = fh.read(20000)
        if "vm-orchestrator.md" in head:
            return f
    return None


def _recent_transcripts(conf, hours=6):
    cut = time.time() - hours * 3600
    return [f for f in Path(conf).expanduser().glob("projects/*stockpilot*/*.jsonl") if f.stat().st_mtime > cut]


def sync_labels(tickets):
    """Keep exactly one status:* label per ticket. Idempotent; touches only tickets whose status changed."""
    for x in tickets:
        want = status(x)
        have = [l for l in x["labels"] if l.startswith("status:")]
        if have == [want]:
            continue
        args = ["issue", "edit", str(x["number"]), "-R", PRIVATE, "--add-label", want]
        for old in have:
            if old != want:
                args += ["--remove-label", old]
        try:
            _gh(*args)
        except subprocess.CalledProcessError:
            for name in STATUS_LABELS:
                _gh("label", "create", name, "-R", PRIVATE, "--force", "--color", "c5def5")
            _gh(*args)


def main_state(api=_api):
    runs = api(f"repos/{ENGINE}/commits/main/check-runs")
    sha = api(f"repos/{ENGINE}/commits/main")["sha"]
    return {"sha": sha, "ci": gather.check_state(runs.get("check_runs", []) if isinstance(runs, dict) else runs)}


def step(account, now=None):
    now = now or _now()
    st = _load()
    lim = st.setdefault("limited_until", {})
    for a in ACCOUNTS:
        until = limit_from_transcripts(_recent_transcripts(a["config_dir"]), now)
        if until and (a["name"] not in lim or _t(lim[a["name"]]) < _t(until)):
            lim[a["name"]] = until
    sent = st.setdefault("sent", {}).setdefault(account, {})
    tickets = collect(now=now)
    sync_labels(tickets)
    ev, new = decide(tickets, {"limited_until": lim, "sent": sent}, now, CFG, account, main=main_state())
    md = board(tickets, {"limited_until": lim}, now)
    key = re.sub(r"_Written by.*?_", "", md)
    if st.get("board") != key:
        try:
            _gh("issue", "edit", str(BOARD_ISSUE), "-R", PRIVATE, "--body", md)
            st["board"] = key
        except subprocess.CalledProcessError as e:
            print(f"watch: board not written: {e}", file=sys.stderr)
    st["limited_until"], st["sent"][account] = new["limited_until"], new["sent"]
    f = _my_transcript(account)
    if f and context_tokens(f) > HANDOFF_AT and f"handoff:{f.name}" not in st["sent"][account]:
        st["sent"][account][f"handoff:{f.name}"] = now
        ev.append({"kind": "handoff", "account": account, "context": context_tokens(f)})
    _save(st)
    return ev


def _gh(*args):
    subprocess.run(["gh", *args], check=True, capture_output=True, text=True)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    w = sub.add_parser("wait", help="block until there is something to do, print it as JSON lines, exit")
    w.add_argument("--account", required=True)
    w.add_argument("--every", type=int, default=120, help="seconds between GitHub reads")
    w.add_argument("--max-minutes", type=int, default=110)
    sub.add_parser("once").add_argument("--account", required=True)
    c = sub.add_parser("claim", help="claim tickets for one builder session")
    c.add_argument("--account", required=True)
    c.add_argument("--session", required=True)
    c.add_argument("--lane", help="lane branch when one builder takes several tickets")
    c.add_argument("numbers", type=int, nargs="+")
    r = sub.add_parser("release", help="take a claim back (stuck or replaced builder)")
    r.add_argument("--account", required=True)
    r.add_argument("--session", required=True)
    r.add_argument("numbers", type=int, nargs="+")
    d = sub.add_parser("done", help="close tickets whose PR merged")
    d.add_argument("--pr", type=int, required=True)
    d.add_argument("numbers", type=int, nargs="+")
    lim = sub.add_parser("limit", help="record that an account hit its usage limit")
    lim.add_argument("--account", required=True)
    lim.add_argument("--until", required=True, help="ISO time the limit resets")
    a = ap.parse_args(argv)

    if a.cmd == "wait":
        end = time.time() + a.max_minutes * 60
        while time.time() < end:
            try:
                ev = step(a.account)
            except Exception as e:   # a GitHub hiccup must not end the watch
                print(f"watch: read failed: {e}", file=sys.stderr)
                ev = []
            if ev:
                for e in ev:
                    print(json.dumps(e), flush=True)
                return 0
            time.sleep(a.every)
        print(json.dumps({"kind": "heartbeat", "account": a.account}), flush=True)
        return 0
    if a.cmd == "once":
        for e in step(a.account):
            print(json.dumps(e))
        return 0
    if a.cmd == "claim":
        taken = {x["number"]: x["claim"] for x in collect(now=_now()) if x["claim"]}
        clash = [n for n in a.numbers if n in taken]
        if clash:
            print(f"already claimed: {clash}", file=sys.stderr)
            return 1
        lane = f" ({a.lane})" if a.lane else ""
        for n in a.numbers:
            _gh("issue", "comment", str(n), "-R", PRIVATE, "-b", f"Claimed by {a.account}: {a.session}{lane}")
            _gh("label", "create", f"pool:{a.account}", "-R", PRIVATE, "--force", "--color", "ededed")
            _gh("issue", "edit", str(n), "-R", PRIVATE, "--add-label", f"pool:{a.account}")
        return 0
    if a.cmd == "release":
        for n in a.numbers:
            _gh("issue", "comment", str(n), "-R", PRIVATE, "-b", f"Released by {a.account}: {a.session}")
            _gh("issue", "edit", str(n), "-R", PRIVATE, "--remove-label", f"pool:{a.account}")
        return 0
    if a.cmd == "done":
        for n in a.numbers:
            _gh("issue", "close", str(n), "-R", PRIVATE, "-c", f"Merged in {ENGINE}#{a.pr}.")
        return 0
    if a.cmd == "limit":
        st = _load()
        st.setdefault("limited_until", {})[a.account] = a.until
        _save(st)
        return 0


if __name__ == "__main__":
    sys.exit(main())
