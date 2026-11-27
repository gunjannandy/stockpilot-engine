from datetime import date, timedelta

from helpers import insert_prices
from stockpilot import store
from stockpilot.analysis import screen

AS_OF = date(2026, 6, 30)


def series(db, symbol, daily_growth, value=3e7, days=300, exchange="NSE"):
    start = AS_OF - timedelta(days - 1)
    rows, prev = [], 100.0
    for i in range(days):
        close = 100 * (1 + daily_growth) ** i
        rows.append((start + timedelta(i), symbol, exchange, "EQ", close, close, close, close, prev, 1000, value, 10))
        prev = close
    insert_prices(db, rows)


def fundamentals(db, symbol, **m):
    for k, v in m.items():
        db.execute("insert into fundamentals values (?, ?, ?, ?, 'test')", [AS_OF, symbol, k, v])


def stock(db, symbol, industry):
    db.execute("insert into stocks values (?, ?, ?, null)", [symbol, symbol.title(), industry])


def build(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    # Three banks: GOOD is cheap, profitable and rising; MEH is average; BAD is dear, weak and falling.
    for sym, growth, roe, pe in (("GOOD", 0.002, 0.20, 10), ("MEH", 0.0005, 0.12, 20), ("BAD", -0.001, 0.05, 40)):
        series(db, sym, growth)
        stock(db, sym, "Banks")
        fundamentals(db, sym, roe=roe, roce=roe, pe=pe, pb=pe / 10, debt_to_equity=0.5, profit_cagr_3y=roe / 2)
    series(db, "TINY", 0.003, value=2e5)                   # ₹2 lakh a day: below the liquidity floor
    stock(db, "TINY", "Banks")
    series(db, "FLAGGED", 0.003)
    stock(db, "FLAGGED", "Banks")
    db.execute("insert into surveillance values (?, 'FLAGGED', 'GSM Stage I')", [AS_OF])
    db.execute("insert into index_levels values (?, 'Nifty 50', 20000, 21, 3, 1.2)", [AS_OF])
    return db


def test_ranks_within_sector_and_explains_exclusions(tmp_path):
    db = build(tmp_path)
    result = screen.run(db, AS_OF, liquidity_floor_cr=1.0)
    order = [c["symbol"] for c in result["candidates"]]
    assert order == ["GOOD", "MEH", "BAD"]
    assert result["candidates"][0]["scores"]["quality"] > result["candidates"][2]["scores"]["quality"]
    assert result["excluded"] == {"TINY": "illiquid (₹0.02 cr a day)", "FLAGGED": "surveillance: GSM Stage I"}


def test_watchlist_stocks_are_always_kept_even_when_excluded(tmp_path):
    db = build(tmp_path)
    db.execute("insert into watchlist (symbol, exchange, added_by) values ('TINY', 'NSE', 'father')")
    result = screen.run(db, AS_OF, liquidity_floor_cr=1.0)
    tiny = next(c for c in result["candidates"] if c["symbol"] == "TINY")
    assert tiny["flags"] == ["illiquid (₹0.02 cr a day)"]
    assert tiny["watchlist"] is True


def test_market_health_reads_breadth(tmp_path):
    db = build(tmp_path)
    health = screen.run(db, AS_OF, liquidity_floor_cr=1.0)["health"]
    assert health["breadth_above_200dma"] == 0.8           # 4 of 5 stocks rising


def test_top_n_reproduces_from_a_fixed_date(tmp_path):
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    first = [c["symbol"] for c in screen.run(build(tmp_path / "a"), AS_OF)["candidates"]]
    second = [c["symbol"] for c in screen.run(build(tmp_path / "b"), AS_OF)["candidates"]]
    assert first == second == ["GOOD", "MEH", "BAD"]


def test_fundamentals_up_to_seven_days_newer_than_the_day_are_used(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    db.execute("insert into fundamentals values ('2026-11-22', 'ABC', 'roe', 0.2, 'yahoo')")
    assert screen._latest_fundamentals(db, date(2026, 11, 20)) == {"ABC": {"roe": 0.2}}     # 2 days newer
    assert screen._latest_fundamentals(db, date(2026, 11, 15)) == {"ABC": {"roe": 0.2}}     # exactly 7
    assert screen._latest_fundamentals(db, date(2026, 11, 14)) == {}                        # 8: too new


def test_a_second_weekly_snapshot_does_not_replace_the_first(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    db.execute("insert into fundamentals values ('2026-11-15', 'ABC', 'pe', 10, 'yahoo')")
    db.execute("insert into fundamentals values ('2026-11-22', 'ABC', 'pe', 12, 'yahoo')")
    assert db.execute("select as_of, value from fundamentals order by as_of").fetchall() == [
        (date(2026, 11, 15), 10.0), (date(2026, 11, 22), 12.0)]
    assert screen._latest_fundamentals(db, date(2026, 11, 14))["ABC"]["pe"] == 10     # the newer one is 8 days ahead
    assert screen._latest_fundamentals(db, date(2026, 11, 16))["ABC"]["pe"] == 12     # 6 days ahead: now it counts
