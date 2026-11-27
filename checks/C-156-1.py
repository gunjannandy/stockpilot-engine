import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops/orchestrator/tests"))
from orch_helpers import *  # noqa: E402,F401,F403
import dispatch  # noqa: E402
import pace  # noqa: E402
import buildstatus  # noqa: E402


def test_pinned_comment_shows_quota_running_tickets_and_prototypes_waiting():
    t1 = ticket(1, "A", claims=[claim("secondary", 300)], pr={"number": 9, "state": "open", "ci": "green"})
    t2 = ticket(2, "U", ui=True, labels=["v3-ui", "prototype-waiting"], claims=[claim("secondary", 300)])
    t3 = ticket(3, "THEIRS", claims=[claim("primary", 300)])
    sess = [session("s1", "A", last_event=7), session("s2", "U", status="idle", last_event=60)]
    w = world([t1, t2, t3], sess, quota={"primary": OK5, "secondary": [
        {"window": "five_hour", "status": "allowed_warning", "resetsAt": "2026-12-01T12:30:00+00:00"}]})
    p = dispatch.plan(w)
    body = p["status_comment"]["body"]
    assert body.startswith("<!-- build-status:secondary -->")
    assert "allowed_warning" in body and "2026-12-01T12:30" in body
    assert "#1" in body and "s1" in body and "#9" in body and "7 min ago" in body
    assert "Prototypes waiting" in body and "U" in body.split("Prototypes waiting")[1]
    assert "THEIRS" not in body, "each account writes only its own tickets"


def test_stuck_sessions_and_what_was_done_appear_in_the_comment():
    s = session("s1", "A", last_event=120, nudged_at=ago(61))
    t = ticket(1, "A", claims=[claim("secondary", 300)], stuck_count=2)
    body = dispatch.plan(world([t], [s]))["status_comment"]["body"]
    assert "needs-planner" in body and "s1" in body


def test_find_own_comment_by_marker_and_update_it():
    comments = [{"id": 5, "body": "<!-- build-status:primary -->\nx"}, {"id": 6, "body": "<!-- build-status:secondary -->\ny"}]
    assert buildstatus.find_comment(comments, "secondary")["id"] == 6
    assert buildstatus.find_comment(comments, "third") is None
    p = dispatch.plan(world([]))
    assert p["status_comment"]["account"] == "secondary"
