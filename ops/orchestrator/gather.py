"""Turn GitHub REST payloads into dispatch inputs. Reads only; never prose for decisions about CI.

Issue bodies are written by docs/spec/v3/tickets.py: `Key `X``, `Blocked by: #1, #2`, `## Owned paths` bullets,
`- [ ] `C-1-1` (unit): ...` check lines. PR check status comes from check runs, never from PR text.
"""
import hashlib
import json
import re
import subprocess
from datetime import datetime

TICKET_LABELS = {"ui": "v3-ui", "vm": "v3-vm"}


def parse_key(body):
    m = re.search(r"Key `([A-Za-z0-9_-]+)`", body or "")
    return m.group(1) if m else None


def parse_blockers(body):
    m = re.search(r"^Blocked by: (.+)$", body or "", re.M)
    return [int(n) for n in re.findall(r"#(\d+)", m.group(1))] if m else []


def parse_owned(body):
    m = re.search(r"^## Owned paths\s*\n((?:\s*- .*\n?)+)", body or "", re.M)
    return re.findall(r"`([^`]+)`", m.group(1)) if m else []


def parse_unticked(body):
    return re.findall(r"^- \[ \] `(C-[\w-]+)`", body or "", re.M)


def parse_claim_declaration(comment):
    """A claim comment may declare owned paths and checks for a ticket that had none."""
    owns, checks = [], []
    section = None
    for line in (comment or "").splitlines():
        head = line.strip().lower()
        if head.startswith("owned paths"):
            section = owns
        elif head.startswith("checks"):
            section = checks
        elif section is not None and line.lstrip().startswith("- "):
            m = re.search(r"`([^`]+)`", line)
            if m:
                section.append(m.group(1))
    return {"owns": owns, "checks": checks}


def parse_left_over(pr_body):
    m = re.search(r"^Left over:\s*\n((?:\s*- .*\n?)+)", pr_body or "", re.M)
    out = []
    for line in (m.group(1).splitlines() if m else []):
        text = line.strip()[2:].strip()
        if text and text.lower() != "none" and not text.lower().startswith('"none"'):
            out.append({"line": text, "files": re.findall(r"`([^`]+)`", text)})
    return out


def left_over_id(key, line):
    return hashlib.sha1(f"{key}\n{line}".encode()).hexdigest()[:10]


def parse_claims(comments):
    out = []
    for c in comments:
        m = re.match(r"Claimed by (\w+): (\S+)", c.get("body", ""))
        if m:
            out.append({"account": m.group(1), "session": m.group(2), "at": c["created_at"], "body": c["body"]})
    return out


def withdrawn(comments):
    """(account, session) pairs that withdrew or were released."""
    gone = set()
    for c in comments:
        m = re.match(r"(?:Withdrawn|Released) by (\w+): (\S+)", c.get("body", ""))
        if m:
            gone.add((m.group(1), m.group(2)))
    return gone


def check_state(check_runs):
    """check_runs: GitHub check-run list for the PR head. green only when every run succeeded."""
    if not check_runs:
        return "none"
    if any(r.get("conclusion") in ("failure", "cancelled", "timed_out") for r in check_runs):
        return "red"
    if all(r.get("conclusion") in ("success", "skipped", "neutral") for r in check_runs):
        return "green"
    return "pending"


def newest(*stamps):
    """The latest of the GitHub timestamps given; None when there are none."""
    got = [s for s in stamps if s]
    return max(got, key=lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))) if got else None


def build_ticket(issue, comments, pr=None, pushed_at=None):
    labels = [l["name"] if isinstance(l, dict) else l for l in issue.get("labels", [])]
    gone = withdrawn(comments)
    claims = [c for c in parse_claims(comments) if (c["account"], c["session"]) not in gone]
    held = {c["body"] for c in claims}
    edited = [c.get("updated_at") or c.get("created_at") for c in comments if c.get("body") in held]
    active_at = newest(*edited, pushed_at, (pr or {}).get("last_push_at")) if claims else None
    owns = parse_owned(issue.get("body"))
    if not owns:
        for c in claims:
            owns = parse_claim_declaration(c["body"])["owns"] or owns
    stuck = sum(1 for c in comments if c.get("body", "").startswith("Replaced stuck builder"))
    return {"number": issue["number"], "key": parse_key(issue.get("body")) or f"#{issue['number']}",
            "title": issue["title"], "labels": labels, "blocked_by": parse_blockers(issue.get("body")),
            "owns": owns, "unticked": parse_unticked(issue.get("body")), "ui": TICKET_LABELS["ui"] in labels,
            "vm": TICKET_LABELS["vm"] in labels,
            "claims": [{k: c[k] for k in ("account", "session", "at")} for c in claims],
            "stuck_count": stuck, "pr": pr, "active_at": active_at}


def gh_api(path, *args):
    res = subprocess.run(["gh", "api", "-X", "GET", path, "--paginate", *args], capture_output=True, text=True, check=True)
    text = res.stdout.strip()
    if text.startswith("[") and "][" in text:   # --paginate prints one array per page
        text = "[" + text.replace("][", ",")[1:-1] + "]"
    return json.loads(text) if text else []


ENGINE = "stockpilot-hq/stockpilot-engine"
PRIVATE = "stockpilot-hq/stockpilot"


def collect(account, state, accounts, mode, api=gh_api, engine_trace="", private_trace=""):
    """Build dispatch inputs.

    state: what only the dispatcher session can read, written by it as JSON:
      {"now": iso, "session": own id, "sessions": [...], "quota": {account: [readings]}, "cloudflare": {...},
       "private_runs": [...]}
    api(path, *args) reads GitHub REST. Tickets are the open issues labelled v3-wave-*; each ticket's PR is the
    engine PR from lane/<key>, and its CI state comes from that PR's check runs.
    """
    issues = [i for i in api(f"repos/{PRIVATE}/issues", "-f", "state=open", "-f", "per_page=100")
              if "pull_request" not in i and any(
                  (l["name"] if isinstance(l, dict) else l).startswith("v3-wave-") for l in i["labels"])]
    tickets, left_over = [], []
    for i in issues:
        comments = api(f"repos/{PRIVATE}/issues/{i['number']}/comments")
        key = parse_key(i.get("body"))
        pr, pushed_at = None, None
        refs = api(f"repos/{ENGINE}/git/matching-refs/heads/lane/{key}") if key and parse_claims(comments) else []
        for ref in refs:
            if ref["ref"] == f"refs/heads/lane/{key}":
                pushed_at = api(f"repos/{ENGINE}/commits/{ref['object']['sha']}")["commit"]["committer"]["date"]
        prs = api(f"repos/{ENGINE}/pulls", "-f", f"head=stockpilot-hq:lane/{key}", "-f", "state=all") if key else []
        if prs:
            p = prs[0]
            sha = p["head"]["sha"]
            runs = api(f"repos/{ENGINE}/commits/{sha}/check-runs")
            runs = runs.get("check_runs", []) if isinstance(runs, dict) else runs
            ci = check_state(runs)
            failing = "\n".join(f"{r['name']}: {(r.get('output') or {}).get('summary') or r.get('conclusion')}"
                                for r in runs if r.get("conclusion") == "failure")
            pr = {"number": p["number"], "state": "merged" if p.get("merged_at") else p["state"], "ci": ci,
                  "failing_output": failing, "last_push_at": p.get("updated_at")}
            left_over += [{"ticket": key, **lo} for lo in parse_left_over(p.get("body"))]
        tickets.append(build_ticket(i, comments, pr, pushed_at))
    return {"now": state["now"], "account": account, "mode": mode, "accounts": accounts, "tickets": tickets,
            "sessions": state["sessions"], "quota": state["quota"], "cloudflare": state["cloudflare"],
            "private_runs": state.get("private_runs", []), "left_over": left_over, "session": state.get("session"),
            "known_left_over": sorted({m for i in issues for m in re.findall(r"left-over:(\w+)", i.get("body") or "")}),
            "trace": {"engine": engine_trace, "private": private_trace, "open_pr": False}}
