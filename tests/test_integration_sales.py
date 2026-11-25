"""Seam 1: one source of truth for sells. `trades` feeds `lots` and `sales`; tax and holdings read the same story."""
from datetime import date

from test_trades_lots import REL, seed

from stockpilot import store, weekly

from stockpilot.analysis import tax
from stockpilot.trades import lots


def test_rebuild_writes_each_matched_sell_to_sales_in_todays_share_units(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    seed(db)
    rows = db.execute("select symbol, isin, kind, sold_on, quantity, price_per_unit from sales "
                      "order by sold_on").fetchall()
    # 8 sold before the 2:1 split are 16 of today's shares at half the price
    assert rows == [("RELIANCE", REL, "stock", date(2023, 6, 1), 16.0, 75.0),
                    ("RELIANCE", REL, "stock", date(2024, 4, 1), 20.0, 90.0)]


def test_sales_are_rebuilt_not_duplicated(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    seed(db)
    seed(db)
    assert db.execute("select count(*) from sales").fetchone()[0] == 2


def test_an_unmatched_sell_is_reported_and_kept_out_of_sales_so_tax_still_runs(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    lots.save_trades(db, [lots.Trade("tradebook", "X1", "stock", "TCS", "INE467B01029", "sell",
                                     date(2024, 1, 5), 4, 3500)])
    assert lots.rebuild(db).unmatched_sells
    assert db.execute("select count(*) from sales").fetchone()[0] == 0


def test_tax_and_holdings_agree_on_what_is_left(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    seed(db)
    lot_rows, sale_rows = weekly._lots(db), weekly._sales(db)
    gains = tax.realise(lot_rows, sale_rows)
    assert round(sum(r["gain"] for r in gains), 2) == 1400.0     # 16 x 25 + 4 x 40 + 10 x 30 + 6 x 90
    left = {l["isin"]: 0.0 for l in tax.open_lots(lot_rows, sale_rows)}
    for l in tax.open_lots(lot_rows, sale_rows):
        left[l["isin"]] += l["quantity"]
    held = {h.isin: h.quantity for h in lots.holdings(db)}
    assert left == held
    assert {l["kind"] for l in lot_rows} <= {"stock", "mf", "rsu"}
