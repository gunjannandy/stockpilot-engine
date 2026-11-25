from datetime import date
from pathlib import Path

from stockpilot import store
from stockpilot.book import smallcase as book_smallcase
from stockpilot.trades import feed, lots, smallcase
from stockpilot.trades.lots import Trade

FIX = Path(__file__).parents[1] / "fixtures" / "trades"
MAIL = FIX.joinpath("smallcase_order.txt").read_text()


def trade(symbol, side, qty, price, day, key=None, isin=None):
    key = key or f"{symbol}{day}{side}{qty:g}"
    return Trade("contract_note", key, "stock", symbol, isin or f"INE{symbol[:6]:0<9}", side, day, qty, price, trade_key=key)


def test_parse_mail_lists_every_order_with_the_basket():
    orders = smallcase.parse_order_mail(MAIL, "Your smallcase order for Value & Momentum", date(2026, 11, 8))
    assert [(o.name, o.side, o.quantity, o.price) for o in orders] == [
        ("INFOSYS LIMITED", "buy", 10.0, 1500.5), ("TATA STEEL", "sell", 100.0, 150.25), ("ITC LIMITED", "buy", 4.0, 1020.0)]
    assert {o.basket for o in orders} == {"Value & Momentum"} and orders[0].order_date == date(2026, 11, 8)


def test_mail_tags_matching_trades_and_the_rest_are_kite(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    lots.save_trades(db, [trade("INFY", "buy", 10, 1500.4, date(2026, 11, 8)),
                          trade("TATASTEEL", "sell", 100, 150.25, date(2026, 11, 9)),   # a day later
                          trade("INFY", "buy", 10, 1500.5, date(2026, 11, 20)),        # same size, other day: Dad's own
                          trade("SBIN", "buy", 5, 800, date(2026, 11, 8))])            # not in the mail
    smallcase.save_orders(db, smallcase.parse_order_mail(MAIL, "Your smallcase order for Value & Momentum", date(2026, 11, 8)))
    smallcase.tag_trades(db)
    got = dict(db.execute("select trade_key, placed_by || '/' || coalesce(basket, '') || '/' || how from trade_tags").fetchall())
    assert got["INFY2026-11-08buy10"] == "smallcase/Value & Momentum/mail"
    assert got["TATASTEEL2026-11-09sell100"] == "smallcase/Value & Momentum/mail"
    assert got["INFY2026-11-20buy10"] == "kite//default" and got["SBIN2026-11-08buy5"] == "kite//default"


def test_one_order_tags_one_trade_only(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    lots.save_trades(db, [trade("INFY", "buy", 10, 1500.5, date(2026, 11, 8), key="a"),
                          trade("INFY", "buy", 10, 1500.5, date(2026, 11, 8), key="b")])
    smallcase.save_orders(db, smallcase.parse_order_mail(MAIL, "Your smallcase order for Value & Momentum", date(2026, 11, 8)))
    smallcase.tag_trades(db)
    assert sorted(db.execute("select placed_by from trade_tags order by trade_key").fetchall()) == [("kite",), ("smallcase",)]


def test_rebalance_day_signature_covers_days_with_no_mail(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    day = date(2026, 3, 5)
    lots.save_trades(db, [trade(f"STOCK{i:02d}", "buy", 1, 100, day) for i in range(smallcase.SIGNATURE_STOCKS)]
                     + [trade("SBIN", "buy", 5, 800, date(2026, 3, 6))])
    smallcase.tag_trades(db)
    rows = db.execute("select placed_by, how, count(*) from trade_tags group by all order by 1").fetchall()
    assert rows == [("kite", "default", 1), ("smallcase", "signature", smallcase.SIGNATURE_STOCKS)]


def test_signature_skips_a_day_the_mails_already_explain(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    day = date(2026, 11, 8)
    lots.save_trades(db, [trade(f"STOCK{i:02d}", "buy", 1, 100, day) for i in range(smallcase.SIGNATURE_STOCKS)])
    smallcase.save_orders(db, smallcase.parse_order_mail(MAIL, "Your smallcase order for Value & Momentum", day))
    smallcase.tag_trades(db)
    assert db.execute("select count(*) from trade_tags where how = 'signature'").fetchone()[0] == 0


def test_tagging_never_changes_trades(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    lots.save_trades(db, [trade("INFY", "buy", 10, 1500.5, date(2026, 11, 8))])
    before = db.execute("select * from trades").fetchall()
    smallcase.save_orders(db, smallcase.parse_order_mail(MAIL, "Your smallcase order for Value & Momentum", date(2026, 11, 8)))
    smallcase.tag_trades(db)
    smallcase.tag_trades(db)   # again: the same answer
    assert db.execute("select * from trades").fetchall() == before
    assert db.execute("select count(*) from trade_tags").fetchone()[0] == 1


def test_feed_reads_the_mail_by_subject_and_store_all_tags(tmp_path):
    from test_trades_feed import FakeBridge, msg
    bridge = FakeBridge([msg("s1", "smallcase <noreply@smallcase.com>", "Your smallcase order for Value & Momentum")],
                        {}, {"s1": MAIL})
    result = feed.fetch(bridge, "ABCDE1234F", since="2026-01-01T00:00:00Z")
    assert len(result.orders) == 3 and result.handled[0]["kind"] == "smallcase_order" and result.handled[0]["outcome"] == "parsed"
    db = store.open(tmp_path / "t.duckdb")
    result.trades = [trade("INFY", "buy", 10, 1500.5, date(2026, 11, 8))]
    feed.store_all(db, result)
    assert db.execute("select placed_by, basket from trade_tags").fetchall() == [("smallcase", "Value & Momentum")]


def test_late_trade_is_tagged_from_orders_saved_in_an_earlier_sync(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    smallcase.save_orders(db, smallcase.parse_order_mail(MAIL, "Your smallcase order for Value & Momentum", date(2026, 11, 8)))
    lots.save_trades(db, [trade("INFY", "buy", 10, 1500.5, date(2026, 11, 8))])   # the contract note comes later
    smallcase.tag_trades(db)
    assert db.execute("select placed_by from trade_tags").fetchall() == [("smallcase",)]


def test_held_by_source_splits_each_holding(tmp_path):
    from stockpilot.book.positions import Position
    db = store.open(tmp_path / "t.duckdb")
    day = date(2026, 11, 8)
    lots.save_trades(db, [trade("INFY", "buy", 10, 1500.5, day, key="sc"), trade("INFY", "buy", 30, 1400, date(2026, 5, 1), key="own"),
                          trade("INFY", "sell", 5, 1600, date(2026, 11, 10), key="out")])
    smallcase.save_orders(db, smallcase.parse_order_mail(MAIL, "Your smallcase order for Value & Momentum", day))
    smallcase.tag_trades(db)
    lots.rebuild(db)   # FIFO: the sale of 5 comes out of Dad's older lot
    infy = Position("equity", "INFY", "INE" + "INFY"[:6] + "00000"[:0], "Infosys", 35, 1420, 1600, "lots")
    infy.isin = db.execute("select isin from lots limit 1").fetchone()[0]
    other = Position("equity", "XYZ", "INE0XYZ00000", "Xyz", 3, 10, 10, "kite")    # known only to Kite
    split = book_smallcase.held_by_source(db, [infy, other])
    assert split["INFY"] == {"kite": 25.0, "smallcase": 10.0, "baskets": {"Value & Momentum": 10.0}}
    assert split["XYZ"] == {"kite": 3.0, "smallcase": 0.0, "baskets": {}}
