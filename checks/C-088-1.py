"""C-088-1: our calls against the Nifty and an equal-weight watchlist, from fixtures."""
from datetime import date, timedelta

from stockpilot.jobs.record import adding_value, score_calls

TODAY = date(2026, 11, 28)
START = date(2026, 6, 1)


def two(first, last):
    return [(START, first), (START + timedelta(days=91), last)]


def test_returns_against_the_nifty_and_the_equal_weight_watchlist():
    closes = {"BUY": two(100, 130), "W1": two(100, 110), "W2": two(100, 120)}
    calls = [{"id": "c1", "symbol": "BUY", "made_on": "2026-06-01", "horizon_days": 63}]
    s = score_calls(calls, closes, two(1000, 1050), ["W1", "W2"], TODAY)
    assert round(s[0]["equal_ret"], 4) == 0.15      # (10% + 20%) / 2
    v = adding_value(s * 1)
    assert (v["n"], v["ours_pct"], v["nifty_pct"], v["equal_weight_pct"]) == (1, 30.0, 5.0, 15.0)
    assert (v["edge_vs_nifty_pct"], v["edge_vs_equal_weight_pct"]) == (25.0, 15.0)
    assert v["adding"] is None                       # one call is not an answer: we wait for 30


def test_thirty_scored_buys_give_a_yes_or_a_no():
    good = {"stock_ret": 0.2, "nifty_ret": 0.05, "equal_ret": 0.1}
    worse = {"stock_ret": 0.02, "nifty_ret": 0.05, "equal_ret": 0.1}
    assert adding_value([good] * 30)["adding"] is True
    assert adding_value([worse] * 30)["adding"] is False
    beats_nifty_not_watchlist = {"stock_ret": 0.08, "nifty_ret": 0.05, "equal_ret": 0.12}
    assert adding_value([beats_nifty_not_watchlist] * 30)["adding"] is False
    assert adding_value([])["adding"] is None
