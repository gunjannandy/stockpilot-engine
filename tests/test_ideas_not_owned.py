"""Ideas are for the whole market: nothing the account already owns may be on the list (the watchlist may overlap)."""
from stockpilot import site


def cand(symbol):
    return {"symbol": symbol, "industry": "x", "composite": 0.7, "scores": {"quality": .5}, "metrics": {"close": 10.0}, "flags": []}


def test_a_held_stock_is_not_an_idea_but_a_watched_one_still_is():
    result = {"candidates": [cand("OWNED"), cand("WATCHED"), cand("NEW")]}
    ranked, row = site._screen_views(result, {}, {"WATCHED"}, {"OWNED"}, {})
    assert [c["symbol"] for c in ranked] == ["WATCHED", "NEW"]
    assert row(1, ranked[0])["watchlist"] is True
