"""Readiness: gaps go at the top of the brief; missing prices or base rates stop buy calls."""
from datetime import date, datetime

from helpers import insert_prices
from stockpilot import readiness, store

DAY = date(2026, 11, 20)


def full(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    insert_prices(db, [(DAY, "TCS", "NSE", "EQ", 1, 2, 1, 1.5, 1, 100, 1e6, 9)])
    db.execute("insert into fundamentals values (?, 'TCS', 'pe', 20, 'yahoo')", [date(2026, 11, 16)])
    db.execute("insert into announcements values (?, 'TCS', 'Board meeting', '', '')", [datetime(2026, 11, 19, 17)])
    db.execute("create table if not exists headlines (symbol varchar, published_at timestamp, title varchar, source varchar, "
               "url varchar, fetched_on date)")
    db.execute("insert into headlines values ('TCS', ?, 'x', 'ET', 'u', ?)", [datetime(2026, 11, 19), DAY])
    db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit) "
               "values ('stock', 'TCS', 'INE467B01029', '2026-01-02', 5, 3400)")
    db.execute("insert into base_rates values ('momentum', 2, 'nifty_up', 91, 900, 0.5, 0.0, ?)", [DAY])
    db.execute("insert into results_calendar values ('TCS', ?, 'Financial Results', 'q')", [date(2027, 1, 10)])
    return db


def test_everything_present_has_no_gaps(tmp_path):
    r = readiness.check(full(tmp_path), DAY)
    assert r == {"gaps": [], "block_buys": False}


def test_missing_prices_for_the_day_block_buys(tmp_path):
    db = full(tmp_path)
    db.execute("delete from prices")
    r = readiness.check(db, DAY)
    assert r["block_buys"] is True
    assert any("prices" in g.lower() and "2026-11-20" in g for g in r["gaps"])


def test_missing_base_rates_block_buys(tmp_path):
    db = full(tmp_path)
    db.execute("delete from base_rates")
    r = readiness.check(db, DAY)
    assert r["block_buys"] is True and any("base rate" in g.lower() for g in r["gaps"])


def test_stale_fundamentals_are_a_gap_but_do_not_block(tmp_path):
    db = full(tmp_path)
    db.execute("delete from fundamentals")
    db.execute("insert into fundamentals values (?, 'TCS', 'pe', 20, 'yahoo')", [date(2026, 11, 1)])
    r = readiness.check(db, DAY)
    assert r["block_buys"] is False and any("fundamentals" in g.lower() for g in r["gaps"])


def test_fundamentals_a_few_days_newer_than_the_day_count(tmp_path):
    db = full(tmp_path)
    db.execute("delete from fundamentals")
    db.execute("insert into fundamentals values (?, 'TCS', 'pe', 20, 'yahoo')", [date(2026, 11, 22)])   # the 7-day tolerance
    assert readiness.check(db, DAY)["gaps"] == []


def test_no_announcements_or_headlines_are_gaps(tmp_path):
    db = full(tmp_path)
    db.execute("delete from announcements")
    db.execute("drop table headlines")                  # R3 not merged yet: a missing table is "no data", not an error
    r = readiness.check(db, DAY)
    assert r["block_buys"] is False
    text = " ".join(r["gaps"]).lower()
    assert "announcements" in text and "headlines" in text


def test_no_lots_is_a_gap(tmp_path):
    db = full(tmp_path)
    db.execute("delete from lots")
    r = readiness.check(db, DAY)
    assert r["block_buys"] is False and any("holdings" in g.lower() for g in r["gaps"])
