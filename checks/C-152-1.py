import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops/orchestrator/tests"))
from orch_helpers import *  # noqa: E402,F401,F403
import dispatch  # noqa: E402
import pace  # noqa: E402
import buildstatus  # noqa: E402

RED = {"number": 9, "state": "open", "ci": "red", "failing_output": "FAILED checks/C-1.py::test_x - boom"}


def test_stopped_builder_with_red_pr_is_resumed_with_the_failing_output():
    t = ticket(1, "A", claims=[claim("secondary", 90)], pr=RED)
    plan = dispatch.plan(world([t], [session("s1", "A", status="idle", last_event=20)]))
    r = plan["resume"][0]
    assert r["session"] == "s1" and "boom" in r["message"] and r["subscribe_own_pr"] is True


def test_merged_prs_session_is_archived():
    t = ticket(1, "A", claims=[claim("secondary", 90)], pr={"number": 9, "state": "merged", "ci": "green"})
    plan = dispatch.plan(world([t], [session("s1", "A", status="idle")]))
    assert [a["session"] for a in plan["archive"]] == ["s1"] and plan["resume"] == []


def test_builders_hold_their_own_pr_subscription_the_dispatcher_subscribes_to_nothing():
    t = ticket(1, "A")
    plan = dispatch.plan(world([t]))
    assert plan["start"][0]["subscribe_own_pr"] is True
    assert "subscribe" not in plan
