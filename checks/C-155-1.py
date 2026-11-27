import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops/orchestrator/tests"))
from orch_helpers import *  # noqa: E402,F401,F403
import dispatch  # noqa: E402
import pace  # noqa: E402
import buildstatus  # noqa: E402

NOW_DT = None


def r(window, status, resets=None):
    return {"window": window, "status": status, "resetsAt": resets}


def state(account_readings, role="spare", mode="burst", reset="Sun 18:30 IST", **kw):
    return pace.account_state(account_readings, role=role, mode=mode, now=NOW, weekly_reset=reset, **kw)


def test_allowed_starts_and_warning_stops():
    assert state([r("five_hour", "allowed")])["can_start"] is True
    s = state([r("five_hour", "allowed_warning", ago(-90))])
    assert s["can_start"] is False and s["refused"] is False


def test_rejected_waits_for_resets_at():
    s = state([r("five_hour", "rejected", ago(-90))])
    assert s["can_start"] is False and s["refused"] is True and s["wait_until"] == ago(-90)
    s = state([r("five_hour", "rejected", ago(1))])
    assert s["can_start"] is True and s["refused"] is False


def test_seven_day_warning_stops_the_driver_only_in_burst():
    seven = [r("five_hour", "allowed"), r("seven_day", "allowed_warning", ago(-5000))]
    assert state(seven, role="driver", reset="Fri 22:30 IST")["can_start"] is False
    assert state(seven, role="spare")["can_start"] is True


def test_seven_day_rejected_stops_everyone():
    assert state([r("seven_day", "rejected", ago(-5000))], role="spare")["can_start"] is False


def test_steady_one_builder_per_wake_and_none_with_any_warning():
    assert state([r("five_hour", "allowed")], mode="steady")["max_starts"] == 1
    assert state([r("five_hour", "allowed")], mode="burst")["max_starts"] is None
    assert state([r("seven_day", "allowed_warning", ago(-5000))], mode="steady")["can_start"] is False


def test_steady_reserve_is_released_in_the_last_twelve_hours_before_the_weekly_reset():
    seven = [r("seven_day", "allowed_warning", ago(-5000))]
    # NOW is Tue 2026-12-01 10:00 UTC; secondary resets Sun 18:30 IST: far off.
    assert state(seven, mode="steady")["can_start"] is False
    # weekly reset Tue 18:30 IST = 13:00 UTC, three hours away
    assert state(seven, mode="steady", reset="Tue 18:30 IST")["can_start"] is True


def test_last_week_before_a_lapse_has_no_reserve():
    seven = [r("seven_day", "allowed_warning", ago(-5000))]
    assert state(seven, role="driver", lapses="2026-12-05")["can_start"] is True
    assert state(seven, role="driver", lapses="2026-12-27")["can_start"] is False


def test_dispatch_starts_nothing_at_warning_and_rejected_and_driver_seven_day_warning():
    t = ticket(1, "A")
    for q, acct in [([r("five_hour", "allowed_warning", ago(-90))], "secondary"),
                    ([r("five_hour", "rejected", ago(-90))], "secondary"),
                    ([r("seven_day", "allowed_warning", ago(-5000))], "primary")]:
        p = dispatch.plan(world([t], account=acct, quota={"primary": q if acct == "primary" else OK5,
                                                           "secondary": q if acct == "secondary" else OK5}))
        assert p["claims"] == [] and p["start"] == [], (q, acct)


def test_the_latest_reading_per_window_wins_across_sessions():
    readings = [r("five_hour", "allowed_warning", ago(-90)), r("five_hour", "allowed", None)]
    assert pace.latest(readings) == readings[-1:]  # the list is oldest first


def test_cloudflare_budgets_gate_ui_tickets():
    ok = {"build_minutes": 0.8, "d1_writes": 0.5, "requests": 0.5, "actions_concurrency": 0.0}
    assert pace.ui_budget_ok(ok) is True
    for k in ok:
        assert pace.ui_budget_ok({**ok, k: 0.81}) is False, k
