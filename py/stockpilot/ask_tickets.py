"""ASKS (spec #24 stories 87 and 88): the father's asks become GitHub tickets, and a closed ticket moves its ask to Done.

An ask is ready for a ticket when the code routed it `auto` and it was understood, or when the owner pressed Approve (the Worker sets
`being_built` and leaves `issue_number` empty). The ticket quotes the original words, carries `ready-for-agent` so the orchestrator
picks it up (CLAUDE.md: new tickets get that label) and one of `auto` or `owner-approved`. An ask the father marked "not what I meant"
gets no ticket. When the ticket closes, the ask is `done` (completed) or `declined` (closed as not planned) and its author gets a yellow mark.

Cheap by design: one D1 read when nothing is open, and one GitHub read (the `from-feedback` issues) when something is. The ticket carries
a marker, so a crash between filing and saving never files twice. REST only (`gh api`); nothing here touches a broker."""
import json

REPO = "gunjannandy/stockpilot"
LABELS = ("ready-for-agent", "from-feedback")
MARKER = "<!-- ask:{id} -->"
TITLE_MAX = 90
OPEN_SQL = ("select a.*, f.person as author from asks a join feedback f on f.id = a.feedback_id "
            "where a.not_meant = 0 and ((a.status = 'understood' and a.route = 'auto') or (a.status = 'being_built')) "
            "order by a.updated_at, a.id")
SIZE_WORD = {"small": "small", "medium": "medium", "large": "large"}


def title(ask: dict) -> str:
    line = " ".join(str(ask["line_en"]).split())
    return "[feedback] " + (line if len(line) <= TITLE_MAX else line[:TITLE_MAX - 1].rstrip() + "…")


def body(ask: dict) -> str:
    quoted = "\n".join("> " + part for part in str(ask["original"]).splitlines() or [""])
    return (f"{ask['line_en']}\n\nPlan: {ask['plan']}\n\nCategory: {ask['tag']}, size: {SIZE_WORD.get(ask['size'], ask['size'])}.\n"
            f"Said by {ask['author']}:\n{quoted}\n\nIn Bengali: {ask['line_bn']}\n\n"
            f"Ask id: {ask['id']}, feedback id: {ask['feedback_id']}. Routed: {ask['route']}.\n{MARKER.format(id=ask['id'])}\n")


def _change(ask: dict, new: str, text: str, at: str) -> dict:
    return {"id": f"chg_ask_{ask['id']}_{new}", "person": ask["author"], "symbol": "feedback", "kind": "ask_status",
            "old_value": "being_built", "new_value": new, "reason": f"{ask['line_en']}: {text}", "at": at}


def _save(query, ask: dict, status: str, issue: int, at: str, mark: dict | None = None) -> None:
    query("update asks set status = ?, issue_number = ?, updated_at = ? where id = ?", [status, issue, at, ask["id"]])
    if mark:
        cols = list(mark)
        query(f"insert or ignore into changes ({','.join(cols)}) values ({','.join('?' * len(cols))})", [mark[c] for c in cols])


def run(query, gh, at: str, repo: str = REPO) -> dict:
    """File the tickets that are due and close the asks whose ticket closed. `gh(args) -> stdout` is the GitHub CLI."""
    out = {"filed": 0, "done": 0}
    asks = query(OPEN_SQL)
    if not asks:
        return out
    issues = json.loads(gh(["api", "-X", "GET", f"repos/{repo}/issues?labels=from-feedback&state=all&per_page=100&sort=updated&direction=desc"]) or "[]")
    by_number = {i["number"]: i for i in issues}
    by_marker = {m: i["number"] for i in issues for a in asks if (m := MARKER.format(id=a["id"])) in (i.get("body") or "")}
    for ask in asks:
        number = ask["issue_number"] or by_marker.get(MARKER.format(id=ask["id"]))
        if number is None:
            who = "auto" if ask["route"] == "auto" else "owner-approved"
            args = ["api", "-X", "POST", f"repos/{repo}/issues", "-f", f"title={title(ask)}", "-f", f"body={body(ask)}"]
            for label in (*LABELS, who):
                args += ["-f", f"labels[]={label}"]
            made = json.loads(gh(args))
            number = made["number"]
            out["filed"] += 1
            _save(query, ask, "being_built", number, at,
                  _change(ask, "being_built", "being built", at) if ask["status"] == "understood" else None)
            continue
        if ask["status"] != "being_built" or ask["issue_number"] is None:
            _save(query, ask, "being_built", number, at, _change(ask, "being_built", "being built", at) if ask["status"] == "understood" else None)
        issue = by_number.get(number)
        if issue and issue.get("state") == "closed":
            declined = issue.get("state_reason") == "not_planned"
            new = "declined" if declined else "done"
            _save(query, ask, new, number, at, _change(ask, new, "declined, not going to be built" if declined else "done", at))
            out["done"] += 1
    return out
