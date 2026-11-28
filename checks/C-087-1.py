"""C-087-1: track-record scoring from fixtures."""
from datetime import date, timedelta

from stockpilot.jobs.record import score_calls

TODAY = date(2026, 11, 28)


def prices(start, first, last, days=91):
    """Two closes: `first` on the start day, `last` at the end of the window."""
    return [(start, first), (start + timedelta(days=days), last)]


def test_a_call_beats_the_nifty_when_its_excess_is_over_the_hurdle():
    start = date(2026, 6, 1)
    closes = {"UP": prices(start, 100, 120), "FLAT": prices(start, 100, 101.5)}
    nifty = prices(start, 1000, 1010)          # +1%
    calls = [{"id": "NSE:UP:1", "symbol": "UP", "made_on": "2026-06-01", "horizon_days": 63},
             {"id": "NSE:FLAT:1", "symbol": "FLAT", "made_on": "2026-06-01", "horizon_days": 63}]
    got = {s["call_id"]: s for s in score_calls(calls, closes, nifty, [], TODAY)}
    assert got["NSE:UP:1"]["beat"] is True and round(got["NSE:UP:1"]["stock_ret"], 2) == 0.2
    assert got["NSE:FLAT:1"]["beat"] is False     # +1.5% against +1%: excess 0.5% is under the 1% hurdle


def test_a_window_not_yet_ended_or_without_prices_is_not_scored():
    start = date(2026, 11, 1)
    calls = [{"id": "a", "symbol": "A", "made_on": "2026-11-01", "horizon_days": 63},
             {"id": "b", "symbol": "B", "made_on": "2026-06-01", "horizon_days": 63},
             {"id": "c", "symbol": "A", "made_on": "2026-06-01", "horizon_days": 21}]
    closes = {"A": prices(start, 1, 2)}
    assert score_calls(calls, closes, prices(date(2026, 6, 1), 1, 2), [], TODAY) == []


def test_same_calls_and_prices_give_the_same_scores():
    start = date(2026, 6, 1)
    calls = [{"id": f"c{i}", "symbol": "A", "made_on": "2026-06-01", "horizon_days": 63} for i in range(5)]
    args = (calls, {"A": prices(start, 100, 110)}, prices(start, 1000, 1000), [], TODAY)
    assert score_calls(*args) == score_calls(*reversed_calls(args))


def reversed_calls(args):
    return (list(reversed(args[0])), *args[1:])
