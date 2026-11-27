"""A leftover worth a few rupees that only the depository statement knows (0.195 units of a liquid fund) is not a holding the
owner wants to see. A small holding Kite or a document shows is still a holding."""
from stockpilot.book import positions


def pos(symbol, qty, price, source="statement"):
    p = positions.Position("equity", symbol, None, symbol, qty, price, None, source)
    p.price = price
    return p


def test_a_statement_only_leftover_under_the_dust_line_is_dropped_and_the_rest_stay():
    kept = positions.without_dust([pos("BIG", 10, 500.0), pos("DUST", 0.195, 1000.0), pos("EDGE", 1, positions.DUST_INR)])
    assert [p.symbol for p in kept] == ["BIG", "EDGE"]


def test_a_small_holding_kite_shows_is_kept():
    assert [p.symbol for p in positions.without_dust([pos("TINY", 1, 200.0, source="kite"), pos("DOCS", 1, 300.0, source="lots")])] == ["TINY", "DOCS"]


def test_a_holding_with_no_price_is_kept_so_it_is_never_hidden_by_a_gap():
    assert [p.symbol for p in positions.without_dust([pos("NOPRICE", 5, None)])] == ["NOPRICE"]
