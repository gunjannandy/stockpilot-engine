import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops/orchestrator/tests"))
from orch_helpers import *  # noqa: E402,F401,F403
import dispatch  # noqa: E402
import pace  # noqa: E402
import buildstatus  # noqa: E402


def mk(ses, **tk):
    t = ticket(1, "A", claims=[claim("secondary", 300)], **tk)
    return world([t], [ses])


def test_silent_for_45_minutes_is_nudged_but_44_is_not():
    assert dispatch.plan(mk(session("s1", "A", last_event=44)))["nudge"] == []
    p = dispatch.plan(mk(session("s1", "A", last_event=45)))
    assert [n["session"] for n in p["nudge"]] == ["s1"] and p["nudge"][0]["reason"] == "silent"


def test_disconnected_or_failed_mid_turn_is_nudged():
    p = dispatch.plan(mk(session("s1", "A", connection="disconnected")))
    assert p["nudge"][0]["reason"] == "disconnected"
    p = dispatch.plan(mk(session("s1", "A", status="failed")))
    assert p["nudge"][0]["reason"] == "failed"


def test_still_stuck_at_the_next_wake_is_replaced_from_the_lane_branch():
    s = session("s1", "A", last_event=120, nudged_at=ago(61))
    p = dispatch.plan(mk(s))
    assert [r["session"] for r in p["replace"]] == ["s1"] and p["replace"][0]["interrupt"] is True
    st = p["start"][0]
    assert (st["ticket"], st["branch"], st["reason"]) == ("A", "lane/A", "replacement")
    assert p["nudge"] == [] and p["needs_planner"] == []


def test_progress_after_a_nudge_is_not_stuck_again():
    s = session("s1", "A", last_event=10, nudged_at=ago(61))
    p = dispatch.plan(mk(s))
    assert p["replace"] == [] and p["nudge"] == []


def test_third_stuck_replacement_labels_needs_planner_and_starts_nobody():
    s = session("s1", "A", last_event=120, nudged_at=ago(61))
    p = dispatch.plan(mk(s, stuck_count=2))
    assert [n["ticket"] for n in p["needs_planner"]] == ["A"]
    assert [r["session"] for r in p["replace"]] == ["s1"] and p["start"] == []
    p2 = dispatch.plan(mk(s, stuck_count=3, labels=["ready-for-agent", "needs-planner"]))
    assert p2["start"] == [] and p2["claims"] == []


def test_prototype_waiting_builder_is_never_touched():
    s = session("s1", "A", status="idle", last_event=500, nudged_at=ago(300), connection="disconnected")
    p = dispatch.plan(mk(s, ui=True, labels=["v3-ui", "prototype-waiting"], unticked=["C-1"]))
    for k in ("nudge", "resume", "replace", "needs_planner", "archive", "start"):
        assert p[k] == [], k
