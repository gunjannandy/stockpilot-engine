"""Lane B step 2: Fidelity vests become lots of a US holding (shares, USD price, vest dates), costed in rupees at the
rate of each vest day. The 5-for-1 split rows are not vests; documents before the split speak in the old units."""
from datetime import date

import pytest

from helpers import insert_prices
from stockpilot.book import positions, rsu
from stockpilot.trades import lots

NOW_ISIN = "US81762P1021"
DAY = date(2026, 11, 20)


def event(db, kind, day, qty, net=None, price=None, grant=None, acquired=None, cost=None, ref="doc1"):
    db.execute("insert into fidelity_events values (?,?,?,?,?,?,?,?,?,?)",
               [ref, kind, day, grant, qty, net, price, round(qty * price, 2) if price else None, acquired, cost])


def rates(db, *pairs):
    for day, rate in pairs:
        db.execute("insert or replace into fx values (?, 'USDINR', ?)", [day, rate])


def test_year_end_vests_become_vest_trades_of_the_net_shares_at_the_vest_day_price(db):
    event(db, "vest", date(2025, 5, 16), 8, net=5, price=1000.0, grant="G1")
    assert rsu.bridge(db) == 1
    row = db.execute("select source, kind, symbol, isin, side, trade_date, quantity, price, currency, status from trades").fetchone()
    assert row == ("fidelity_docs", "rsu", "NOW", NOW_ISIN, "vest", date(2025, 5, 16), 5, 1000.0, "USD", "confirmed")


def test_a_statement_delivery_a_few_days_after_a_year_end_vest_is_the_same_vest(db):
    event(db, "vest", date(2025, 2, 7), 3, net=3, price=1008.0, grant="G1", ref="year-end")
    event(db, "vest", date(2025, 2, 10), 3, net=3, price=1021.0, ref="statement")
    assert rsu.bridge(db) == 1


def test_a_statement_only_vest_counts_and_a_second_run_adds_nothing(db):
    event(db, "vest", date(2024, 5, 21), 7, net=7, price=777.0, ref="statement")
    assert rsu.bridge(db) == 1 and rsu.bridge(db) == 0
    assert db.execute("select count(*) from trades").fetchone()[0] == 1


def test_a_vest_the_email_route_already_stored_is_not_stored_twice(db):
    lots.save_trades(db, [lots.Trade("fidelity", "ref1", "rsu", "NOW", NOW_ISIN, "vest", date(2025, 5, 14), 5, 1000.0, "USD")])
    event(db, "vest", date(2025, 5, 16), 8, net=5, price=1000.0, grant="G1")      # the same vest, two days apart
    assert rsu.bridge(db) == 0


def test_sales_become_sells_and_a_statement_sale_beside_a_summary_sale_is_the_same_sale(db):
    event(db, "vest", date(2025, 2, 7), 7, net=7, price=1000.0, grant="G1")
    event(db, "sale", date(2025, 2, 10), 2, price=1024.78, acquired=date(2025, 2, 7), cost=2000.0, ref="summary")
    event(db, "sale", date(2025, 2, 11), 2, price=1024.81, cost=2000.0, ref="statement")     # settles a day later
    assert rsu.bridge(db) == 2
    assert db.execute("select side, quantity, price from trades where side = 'sell'").fetchall() == [("sell", 2, 1024.78)]


def test_the_split_is_stored_once_and_old_units_are_scaled_in_the_lots(db):
    event(db, "vest", date(2025, 5, 16), 5, net=5, price=1000.0, grant="G1")           # 5 shares at $1000, before the split
    event(db, "vest", date(2026, 2, 9), 6, net=6, price=100.0, ref="statement")        # 6 shares at $100, after it
    rsu.bridge(db), rsu.bridge(db)
    assert db.execute("select count(*) from corporate_actions where isin = ? and kind = 'split'", [NOW_ISIN]).fetchone()[0] == 1
    lots.rebuild(db)
    got = db.execute("select acquired_on, quantity, cost_per_unit from lots order by acquired_on").fetchall()
    assert got == [(date(2025, 5, 16), 25, 200.0), (date(2026, 2, 9), 6, 100.0)]


def test_a_sale_before_the_split_closes_old_shares_in_new_units(db):
    event(db, "vest", date(2025, 2, 7), 7, net=7, price=1000.0, grant="G1")
    event(db, "sale", date(2025, 2, 10), 2, price=1024.0, acquired=date(2025, 2, 7), cost=2000.0)
    rsu.bridge(db)
    lots.rebuild(db)
    assert db.execute("select quantity, closed_quantity from lots").fetchall() == [(35, 10)]


def test_held_shows_one_us_line_costed_at_each_vest_days_rate_and_priced_today(db):
    event(db, "vest", date(2026, 2, 9), 6, net=6, price=100.0)
    event(db, "vest", date(2026, 5, 18), 4, net=4, price=120.0)
    rates(db, (date(2026, 2, 9), 90.0), (date(2026, 5, 18), 95.0), (DAY, 92.0))
    insert_prices(db, [(DAY, "NOW", "NYSE", "", 0, 0, 0, 110.0, 0, 0, 0, 0)])
    rsu.bridge(db)
    lots.rebuild(db)
    [p] = positions.held(db, DAY)
    assert (p.kind, p.symbol, p.quantity) == ("foreign", "NOW", 10)
    assert p.avg_cost == pytest.approx((6 * 100 * 90 + 4 * 120 * 95) / 10)       # rupees, each lot at its own day's rate
    assert p.price == pytest.approx(110 * 92)


def test_a_vest_day_with_no_rate_uses_the_nearest_earlier_rate_not_todays(db):
    event(db, "vest", date(2026, 2, 9), 6, net=6, price=100.0)
    rates(db, (date(2026, 2, 6), 90.0), (DAY, 92.0))                # a weekend sits between
    rsu.bridge(db)
    lots.rebuild(db)
    [p] = positions.held(db, DAY)
    assert p.avg_cost == pytest.approx(100 * 90)




def test_two_copies_of_one_report_count_once(db):
    for ref in ("report-a", "report-b"):                                     # the same year-end PDF saved twice in Drive
        event(db, "vest", date(2025, 5, 16), 8, net=5, price=1000.0, grant="G1", ref=ref)
    assert rsu.bridge(db) == 1
    assert db.execute("select quantity from trades").fetchone()[0] == 5


def test_a_statement_vest_takes_the_day_the_sale_says_the_shares_were_acquired(db):
    event(db, "vest", date(2024, 5, 21), 7, net=7, price=777.0, ref="statement")                    # the delivery day
    event(db, "sale", date(2024, 5, 20), 3, price=769.0, acquired=date(2024, 5, 17), cost=2300.0, ref="summary")
    rsu.bridge(db)
    lots.rebuild(db)
    assert db.execute("select trade_date from trades where side = 'vest'").fetchone()[0] == date(2024, 5, 17)
    assert db.execute("select quantity, closed_quantity from lots").fetchall() == [(35, 15)]       # the sale found its shares
    assert lots.rebuild(db).unmatched_sells == []
