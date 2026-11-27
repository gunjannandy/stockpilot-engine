import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops/orchestrator/tests"))
from orch_helpers import *  # noqa: E402,F401,F403
import dispatch  # noqa: E402
import pace  # noqa: E402
import buildstatus  # noqa: E402


def test_waiting_prototype_is_never_resumed_and_counts_toward_cap_of_three():
    waiting = [ticket(10 + i, f"W{i}", ui=True, labels=["v3-ui", "prototype-waiting"], unticked=["C-1"],
                      claims=[claim("primary", 600)]) for i in range(3)]
    sess = [session(f"p{i}", f"W{i}", account="primary", status="idle", last_event=300) for i in range(3)]
    new_ui = ticket(20, "NEWUI", ui=True, labels=["v3-ui", "ready-for-agent"])
    plan = dispatch.plan(world(waiting + [new_ui], sess, account="primary"))
    assert plan["resume"] == [] and plan["nudge"] == [] and plan["replace"] == []
    assert plan["claims"] == [], "cap of 3 waiting prototypes blocks a fourth UI ticket"


def test_no_ui_ticket_starts_above_eighty_percent_of_build_minutes():
    ui = ticket(20, "UI1", ui=True, labels=["v3-ui", "ready-for-agent"])
    plain = ticket(21, "PLAIN")
    w = world([ui, plain], account="primary")
    w["cloudflare"]["build_minutes"] = 0.81
    plan = dispatch.plan(w)
    assert keys(plan["claims"], "ticket") == ["PLAIN"]
    w["cloudflare"]["build_minutes"] = 0.8
    assert "UI1" in keys(dispatch.plan(w)["claims"], "ticket")
