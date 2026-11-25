"""The feedback inbox (R12). The owners type a wish or a complaint on the dashboard; it is stored at once as 'new'
(the page shows "Received"). Each evening one cheap model call restates and sizes the day's new items, and CODE picks the
route: small and not about money, rules, tax or the Kite read-only rule -> 'auto' (an issue labelled feedback-auto for the
next orchestrator session); anything else -> 'backlog' (feedback-backlog, waiting for an owner's call). This module never
changes code itself: it files the issue and records it. An issue that closes marks the item 'applied'."""
import json
import re
from datetime import date

from stockpilot import house_rules, journal

KINDS = ("want", "like", "dislike", "bug")
MAX_TEXT = 1000
AUTO, BACKLOG, APPROVED = "feedback-auto", "feedback-backlog", "feedback-approved"
SHOWN = {"new": "received", "auto": "planned", "backlog": "backlog", "applied": "applied", "declined": "declined"}
# Words that make an item a money or rule change whatever the model says: code is the second judge.
RISKY = re.compile(r"\b(money|rupees?|rs|inr|lakh|crore|budget|stop[- ]?loss|threshold|rules?|tax(es)?|stcg|ltcg|brokerage|"
                   r"orders?|kite|read[- ]only|zerodha|allocation|sizing|probability|hurdle)\b", re.I)


def add(db, text, kind, by) -> int:
    text = str(text or "").strip()
    if not text:
        raise ValueError("The feedback is empty.")
    if len(text) > MAX_TEXT:
        raise ValueError(f"Please keep feedback under {MAX_TEXT} letters.")
    kind = (str(kind).strip().lower() or None) if kind else None
    if kind and kind not in KINDS:
        raise ValueError(f"The kind must be one of {', '.join(KINDS)}.")
    return db.execute("insert into feedback (author, kind, text) values (?, ?, ?) returning id",
                      [by or "", kind, text]).fetchone()[0]


def route(text: str, answer: dict) -> str:
    """'auto' only for a small item the model did not call a rule or money change and the words do not touch."""
    safe = (answer.get("size") == "small" and answer.get("category") != "rule or money change"
            and not RISKY.search(f"{text} {answer.get('plan', '')} {answer.get('restatement', '')}"))
    return "auto" if safe else "backlog"


def _issue_number(url: str) -> int | None:
    m = re.search(r"/issues/(\d+)", url or "")
    return int(m.group(1)) if m else None


def _body(row, answer) -> str:
    who = row["author"] or "an owner"
    return (f"{answer['restatement']}\n\nPlan: {answer['plan']}\n\nCategory: {answer['category']}, size: {answer['size']}.\n"
            f"Said by {who}{' (' + row['kind'] + ')' if row['kind'] else ''}:\n> {row['text']}\n\nfeedback id: {row['id']}")


def _rows(db, where: str, args=()) -> list[dict]:
    cols = ("id", "\"at\"", "author", "kind", "text", "status", "triage", "backlog_id", "applied_at")
    return [dict(zip(("id", "at", "author", "kind", "text", "status", "triage", "backlog_id", "applied_at"), r)) for r in db.execute(f"select {', '.join(cols)} from feedback where {where} order by id", list(args)).fetchall()]


def _sync_closed(db, gh, day: date, changes: list) -> int:
    """An issue that closed (and that we did not close by declining) means the change was made."""
    open_items = _rows(db, "status in ('auto', 'backlog') and backlog_id is not null")
    if not open_items:
        return 0
    closed = set()
    for label in (AUTO, APPROVED):
        found = json.loads(gh("issue", "list", "--label", label, "--state", "closed", "--json", "number", "--limit", "100") or "[]")
        closed |= {i["number"] for i in found}
    done = 0
    for item in open_items:
        if item["backlog_id"] in closed:
            db.execute("update feedback set status = 'applied', applied_at = current_timestamp where id = ?", [item["id"]])
            plan = (json.loads(item["triage"]) if isinstance(item["triage"], str) else item["triage"] or {}).get("plan") or item["text"]
            changes.append(f"Done: {plan}")
            done += 1
    return done


def triage(db, day: date, analyse, runners, gh) -> dict:
    """Close the loop on applied issues, then triage the new items with one model call. No new items: no model call."""
    changes: list[str] = []
    applied = 0
    try:
        applied = _sync_closed(db, gh, day, changes)
    except Exception as err:  # noqa: BLE001 - the issue list is a convenience; triage still runs
        journal.problem(db, "feedback", f"Could not read feedback issues: {err}", key="feedback:issues")
    new = _rows(db, "status = 'new'")
    out = {"status": "skipped", "auto": 0, "backlog": 0, "applied": applied}
    if new:
        brief = {"items": [{"id": r["id"], "text": r["text"], "kind": r["kind"]} for r in new]}
        try:
            answers = {a["id"]: a for a in analyse(brief, "feedback", runners)["decisions"]["items"]}
        except Exception as err:  # noqa: BLE001 - the items stay 'new' and are tried again tomorrow
            journal.problem(db, "feedback", f"Feedback triage failed: {err}", key="feedback:triage")
            out["status"] = "failed"
            answers = {}
        else:
            out["status"] = "ok"
        for row in new:
            answer = answers.get(row["id"])
            if not answer:
                continue
            rule = (answer.get("house_rule") or "").strip()
            if rule and house_rules.acceptable(rule):
                try:        # a proposed edit to the house rules: no code change, so no issue; it waits for the Approve click
                    house_rules.propose(db, row["id"], rule)
                except ValueError as err:
                    journal.problem(db, "feedback", f"House rule not proposed for feedback {row['id']}: {err}", key=f"feedback:rule:{row['id']}")
                else:
                    db.execute("update feedback set status = 'backlog', triage = ? where id = ?", [json.dumps(answer), row["id"]])
                    out["backlog"] += 1
                    changes.append(f"Waiting for your call: House rule: {rule}")
                    continue
            status = route(row["text"], answer)
            label = AUTO if status == "auto" else BACKLOG
            try:
                gh("label", "create", label, "--force", "--color", "fbca04" if label == BACKLOG else "0e8a16",
                   "--description", "Owner feedback, filed by stockpilot")
                url = gh("issue", "create", "--label", label, "--title", f"[feedback] {answer['restatement'][:80]}",
                         "--body", _body(row, answer))
            except Exception as err:  # noqa: BLE001 - this item stays 'new'
                journal.problem(db, "feedback", f"Could not file the issue for feedback {row['id']}: {err}", key=f"feedback:issue:{row['id']}")
                continue
            db.execute("update feedback set status = ?, triage = ?, backlog_id = ? where id = ?",
                       [status, json.dumps(answer), _issue_number(url), row["id"]])
            out[status] += 1
            changes.append(f"{'Planned' if status == 'auto' else 'Waiting for your call'}: {answer['plan']}")
    if changes or out["status"] != "skipped":
        db.execute("delete from feedback_changes")                # only the last triage is shown
        db.execute("insert into feedback_changes values (?, ?)", [day, json.dumps(changes)])
    out["changed"] = bool(changes)
    return out


def decide(db, feedback_id, decision, gh=None) -> str:
    if decision not in ("approve", "decline"):
        raise ValueError("The decision must be approve or decline.")
    row = db.execute("select status, backlog_id from feedback where id = ?", [feedback_id]).fetchone()
    if not row:
        raise ValueError(f"There is no feedback number {feedback_id}.")
    status, issue = row
    if status in ("applied", "declined"):
        raise ValueError(f"Feedback {feedback_id} is already {SHOWN[status]}.")
    number = str(issue) if issue else None
    if decision == "approve":
        if status == "new":
            raise ValueError("That feedback has not been looked at yet; it is triaged in the evening.")
        if house_rules.approve_for_feedback(db, feedback_id):       # a house rule needs no build: it is live now
            db.execute("update feedback set status = 'applied', applied_at = current_timestamp where id = ?", [feedback_id])
            return "Approved. The new House rule is live from tonight's run."
        db.execute("update feedback set status = 'auto' where id = ?", [feedback_id])
        if gh and number:
            gh("issue", "edit", number, "--add-label", APPROVED, "--remove-label", BACKLOG)
        return "Approved. It will be picked up for the next change."
    house_rules.reject_for_feedback(db, feedback_id)
    db.execute("update feedback set status = 'declined' where id = ?", [feedback_id])
    if gh and number:
        gh("issue", "close", number, "--reason", "not planned")
    return "Declined. It will not be built."


def site_payload(db) -> dict:
    items = []
    for r in _rows(db, "true"):
        triage_ = json.loads(r["triage"]) if isinstance(r["triage"], str) else (r["triage"] or {})
        items.append({"id": r["id"], "at": str(r["at"])[:10], "by": r["author"], "kind": r["kind"], "text": r["text"],
                      "status": SHOWN[r["status"]], "plan": triage_.get("plan"), "said_as": triage_.get("restatement"),
                      "applied_on": str(r["applied_at"])[:10] if r["applied_at"] else None})
    extra = db.execute("select built_on, changes from feedback_changes order by built_on desc limit 1").fetchone()
    changed = (json.loads(extra[1]) if isinstance(extra[1], str) else extra[1]) if extra else []
    return {"items": list(reversed(items)), "last_triage": str(extra[0]) if extra else None, "changed": changed}
