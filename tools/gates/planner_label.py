"""Planner-label gate: a PR touching workflows, gates or a check that has passed on main needs the `planner` label,
and the label must have been added by stockpilot-bot (read from the issue's label events), never by a builder.
"""
import fnmatch
from datetime import datetime, timezone

LABEL = "planner"
BOT_LOGINS = {"stockpilot-bot[bot]", "stockpilot-bot"}
PROTECTED = (".github/workflows/*", "tools/gates/*")
NOT_CHECKS = {"checks/trace.csv", "checks/status.json"}


def _is_passed_check(path, main_files):
    return path.startswith("checks/") and path not in NOT_CHECKS and path in set(main_files)


def needs_label(changed, main_files):
    return any(any(fnmatch.fnmatch(p, g) for g in PROTECTED) or _is_passed_check(p, main_files) for p in changed)


def _when(text):
    t = datetime.fromisoformat(text.replace("Z", "+00:00"))
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def label_added_by_bot(events, head_time=None):
    """The label stands only if its latest event is a bot adding it, and (when head_time is given) only if that
    happened after the head commit, so a push made after the label is not covered by it."""
    last = None
    for e in events:
        if (e.get("label") or {}).get("name") == LABEL and e.get("event") in ("labeled", "unlabeled"):
            last = e
    if not (last and last["event"] == "labeled" and (last.get("actor") or {}).get("login") in BOT_LOGINS):
        return False
    return head_time is None or _when(last["created_at"]) > _when(head_time)


def verdict(changed, main_files, events, head_time=None):
    if not needs_label(changed, main_files):
        return []
    if label_added_by_bot(events, head_time):
        return []
    return [f"this PR touches a protected path and needs the `{LABEL}` label added by stockpilot-bot after the latest push"]
