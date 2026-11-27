import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops/orchestrator/tests"))
from orch_helpers import *  # noqa: E402,F401,F403
import dispatch  # noqa: E402
import pace  # noqa: E402
import buildstatus  # noqa: E402


def test_earliest_claim_wins_and_the_other_account_withdraws():
    t = ticket(1, "A", claims=[claim("primary", 20), claim("secondary", 10)])
    mine = dispatch.plan(world([t], account="secondary"))
    assert [w["ticket"] for w in mine["withdraw"]] == ["A"] and mine["start"] == [] and mine["claims"] == []
    theirs = dispatch.plan(world([t], account="primary"))
    assert theirs["withdraw"] == []


def test_claim_times_tie_on_session_id():
    t = ticket(1, "A", claims=[claim("primary", 5, "s-b"), claim("secondary", 5, "s-a")])
    assert dispatch.plan(world([t], account="secondary"))["withdraw"] == []
    assert [w["ticket"] for w in dispatch.plan(world([t], account="primary"))["withdraw"]] == ["A"]


def test_claim_with_no_push_for_six_hours_while_account_refused_is_released():
    refused = [{"window": "five_hour", "status": "rejected", "resetsAt": "2026-12-01T14:00:00+00:00"}]
    quota = {"primary": refused, "secondary": OK5}
    stale = ticket(1, "A", claims=[claim("primary", 400)], pr={"number": 9, "state": "open", "ci": "pending",
                                                                "last_push_at": ago(361)})
    fresh = ticket(2, "B", claims=[claim("primary", 400)], pr={"number": 10, "state": "open", "ci": "pending",
                                                                "last_push_at": ago(30)})
    plan = dispatch.plan(world([stale, fresh], account="secondary", quota=quota))
    assert [r["ticket"] for r in plan["release"]] == ["A"]
    assert plan["release"][0]["account"] == "primary"


def test_no_release_while_the_account_is_allowed():
    stale = ticket(1, "A", claims=[claim("primary", 900)], pr=None)
    assert dispatch.plan(world([stale], account="secondary"))["release"] == []


def test_refused_account_with_expired_reset_is_not_released():
    past = [{"window": "five_hour", "status": "rejected", "resetsAt": "2026-12-01T09:00:00+00:00"}]
    stale = ticket(1, "A", claims=[claim("primary", 900)])
    assert dispatch.plan(world([stale], quota={"primary": past, "secondary": OK5}))["release"] == []
