"""Turn GitHub REST payloads into dispatch inputs. Reads only; never prose for decisions about CI.

Issue bodies are written by docs/spec/v3/tickets.py: `Key `X``, `Blocked by: #1, #2`, `## Owned paths` bullets,
`- [ ] `C-1-1` (unit): ...` check lines. PR check status comes from check runs, never from PR text.
"""
import hashlib
import json
import re
import subprocess

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


def build_ticket(issue, comments, pr=None):
    labels = [l["name"] if isinstance(l, dict) else l for l in issue.get("labels", [])]
    gone = withdrawn(comments)
    claims = [c for c in parse_claims(comments) if (c["account"], c["session"]) not in gone]
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
            "stuck_count": stuck, "pr": pr}


def gh_api(path, *args):
    res = subprocess.run(["gh", "api", "-X", "GET", path, "--paginate", *args], capture_output=True, text=True, check=True)
    text = res.stdout.strip()
    if text.startswith("[") and "][" in text:   # --paginate prints one array per page
        text = "[" + text.replace("][", ",")[1:-1] + "]"
    return json.loads(text) if text else []
