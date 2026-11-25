"""The house rules: a few plain lines every analyst call reads. The base lines are `prompts/house-rules.md` (in git). Owner
feedback about how the analyst should write or judge becomes a PROPOSED edit (`house_rule_edits`); it goes live only on an
Approve click, through the same feedback Approve button as any other change. Never about money, thresholds, tax or orders:
those words are refused here, and such feedback takes the ordinary backlog route."""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "prompts" / "house-rules.md"
MAX_ACTIVE = 12          # the file stays small: past this, retire one first
MAX_TEXT = 200
NUMBERISH = re.compile(r"[\d%₹]")
LINES = re.compile(r"\b(buy|sell|stop|target)[- ](line|price|level)\b", re.I)


def base() -> str:
    return BASE.read_text().strip()


def active(db) -> list[str]:
    return [t for (t,) in db.execute("select text from house_rule_edits where status = 'approved' order by id").fetchall()]


def acceptable(text) -> bool:
    from stockpilot import feedback
    text = (text or "").strip()
    # no digits, %, or ₹: a number in a rule is a threshold, and thresholds change only through chat
    return bool(text) and len(text) <= MAX_TEXT and not feedback.RISKY.search(text) and not NUMBERISH.search(text) \
        and not LINES.search(text)


def propose(db, feedback_id, text) -> int:
    text = (text or "").strip()
    if not acceptable(text):
        raise ValueError("That is not a house rule: it is empty, too long, or about money, tax or the rules.")
    if len(active(db)) >= MAX_ACTIVE:
        raise ValueError(f"The house rules are kept small ({MAX_ACTIVE} extra lines); retire one first.")
    return db.execute("insert into house_rule_edits (text, feedback_id) values (?, ?) returning id", [text, feedback_id]).fetchone()[0]


def _set(db, where: str, args: list, status: str) -> int:
    n = db.execute(f"select count(*) from house_rule_edits where {where}", args).fetchone()[0]
    if n:
        db.execute(f"update house_rule_edits set status = ?, decided_at = current_timestamp where {where}", [status, *args])
    return n


def approve(db, edit_id) -> int:
    if len(active(db)) >= MAX_ACTIVE:
        raise ValueError(f"The house rules are kept small ({MAX_ACTIVE} extra lines); retire one first.")
    return _set(db, "id = ? and status = 'proposed'", [edit_id], "approved")


def reject_for_feedback(db, feedback_id) -> int:
    return _set(db, "feedback_id = ? and status = 'proposed'", [feedback_id], "rejected")


def approve_for_feedback(db, feedback_id) -> int:
    ids = [i for (i,) in db.execute("select id from house_rule_edits where feedback_id = ? and status = 'proposed'", [feedback_id]).fetchall()]
    return sum(approve(db, i) for i in ids)


def retire(db, edit_id) -> int:
    return _set(db, "id = ? and status = 'approved'", [edit_id], "retired")
