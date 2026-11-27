import json
from datetime import date

from helpers import insert_prices
from stockpilot import store
from stockpilot.book import smallcase as book_smallcase
from stockpilot.trades import lots, smallcase
from stockpilot.trades.lots import Trade


def trade(symbol, side, qty, price, day, key):
    return Trade("contract_note", key, "stock", symbol, f"INE{symbol}00000"[:12], side, day, qty, price, trade_key=key)


def close(symbol, day, value):
    return (day, symbol, "NSE", "EQ", value, value, value, value, value, 1000, 1e6, 10)


def seed(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    lots.save_trades(db, [trade("AAA", "buy", 10, 100, date(2026, 1, 10), "a1"), trade("AAA", "sell", 10, 130, date(2026, 2, 20), "a2"),
                          trade("BBB", "buy", 10, 200, date(2026, 1, 15), "b1")])
    db.execute("insert into smallcase_orders values ('o1', 'Value', '2026-01-10', 'AAA', 'buy', 10, 100, 'm'),"
               " ('o2', 'Value', '2026-02-20', 'AAA', 'sell', 10, 130, 'm')")
    smallcase.tag_trades(db)
    lots.rebuild(db)
    insert_prices(db, [close("AAA", date(2026, 1, 30), 110), close("BBB", date(2026, 1, 30), 205),
                       close("AAA", date(2026, 2, 27), 150), close("BBB", date(2026, 2, 27), 220)])
    for day, level in [(date(2026, 1, 10), 20000), (date(2026, 1, 15), 20000), (date(2026, 1, 30), 20500),
                       (date(2026, 2, 20), 21000), (date(2026, 2, 27), 22000)]:
        db.execute("insert into index_levels values (?, 'Nifty 50', ?, 20, 3, 1)", [day, level])
    return db


def test_months_show_gain_fees_tax_and_the_nifty_for_each_route(tmp_path):
    db = seed(tmp_path)
    got = book_smallcase.comparison(db, date(2026, 2, 28))
    jan, feb = got["months"]
    assert (jan["month"], feb["month"]) == ("2026-01", "2026-02")
    sc = jan["smallcase"]
    assert (sc["invested"], sc["gain"], sc["nifty_gain"]) == (1000, 100, 25)      # open: 10 x (110 - 100); 1000 x (20500/20000 - 1)
    assert sc["fees"] == 500 + 118 and sc["tax"] == 0                             # 6000/12, one rebalance of 100 + 18% tax
    sc = feb["smallcase"]
    assert (sc["invested"], sc["gain"], sc["nifty_gain"]) == (1000, 300, 50)      # sold 10 x (130 - 100); 1000 x (21000/20000 - 1)
    assert sc["fees"] == 1000 + 236 and sc["tax"] == 62.4                         # short-term: 20% of 300, plus 4% cess
    assert sc["after_fees_and_tax"] == 300 - 1236 - 62.4
    own = feb["own"]
    assert (own["invested"], own["gain"], own["fees"], own["tax"], own["nifty_gain"]) == (2000, 200, 0, 0, 200)
    assert jan["own"]["gain"] == 50


def test_summary_is_plain_words_with_rupees(tmp_path):
    db = seed(tmp_path)
    got = book_smallcase.comparison(db, date(2026, 2, 28))
    text = " ".join(got["lines"])
    assert "smallcase" in text and "₹" in text and "Nifty" in text
    assert "alpha" not in text.lower() and "xirr" not in text.lower()
    assert got["fees"] == {"yearly": 6000, "per_rebalance": 100, "tax_on_fees": 0.18}


def test_no_smallcase_trades_gives_an_empty_comparison(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    got = book_smallcase.comparison(db, date(2026, 2, 28))
    assert got["months"] == [] and got["lines"] == []


def test_write_puts_the_json_beside_the_other_pages(tmp_path):
    db = seed(tmp_path)
    book_smallcase.write(db, tmp_path / "site", date(2026, 2, 28))
    body = json.loads((tmp_path / "site" / "data" / "smallcase.json").read_text())
    assert body["as_of"] == "2026-02-28" and len(body["months"]) == 2
