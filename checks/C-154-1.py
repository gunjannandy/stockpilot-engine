import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops/orchestrator/tests"))
from orch_helpers import *  # noqa: E402,F401,F403
import dispatch  # noqa: E402
import pace  # noqa: E402
import buildstatus  # noqa: E402


def test_an_open_hotfix_plans_a_builder_even_above_ninety_percent():
    warn = [{"window": "five_hour", "status": "allowed_warning", "resetsAt": ago(-100)}]
    hot = ticket(1, "HOT", owns=[], labels=["hotfix"])
    plan = dispatch.plan(world([hot], quota={"primary": OK5, "secondary": warn}))
    assert keys(plan["claims"], "ticket") == ["HOT"]
    assert plan["start"][0]["ticket"] == "HOT" and plan["start"][0]["reason"] == "hotfix"


def test_hotfix_does_not_start_when_the_account_is_refused():
    rej = [{"window": "five_hour", "status": "rejected", "resetsAt": ago(-100)}]
    hot = ticket(1, "HOT", owns=[], labels=["hotfix"])
    assert dispatch.plan(world([hot], quota={"primary": OK5, "secondary": rej}))["start"] == []


def test_hotfix_goes_first_and_ignores_running_tickets():
    busy = ticket(2, "BUSY", owns=["o/**"], claims=[claim("secondary", 10)])
    hot = ticket(1, "HOT", owns=[], labels=["hotfix"])
    assert keys(dispatch.plan(world([busy, hot]))["claims"], "ticket") == ["HOT"]
