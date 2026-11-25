import json
from datetime import date
from pathlib import Path

from pytest import approx

from stockpilot import store

from stockpilot.sources import fundamentals

SAMPLE = json.loads((Path(__file__).parents[1] / "fixtures" / "yfinance_sample.json").read_text())


def fetch(symbol):
    return SAMPLE.get(f"{symbol}.NS")


def metrics(db, symbol):
    return dict(db.execute("select metric, value from fundamentals where symbol = ?", [symbol]).fetchall())


def test_large_cap_ratios_and_growth(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    fundamentals.refresh(db, ["RELIANCE"], date(2026, 11, 22), fetch)
    m = metrics(db, "RELIANCE")
    assert m["pe"] == approx(22.70, rel=1e-3)
    assert m["debt_to_equity"] == approx(0.443, rel=1e-3)       # Yahoo reports percent
    assert m["roce"] == approx(0.0899, rel=1e-2)                  # 1472.18 / (21781.4 - 5412.54)
    assert m["revenue_cagr_3y"] == approx(0.0639, rel=1e-2)       # (10572.19 / 8778.35) ** (1/3) - 1


def test_small_cap_gaps_are_filled_from_statements(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    fundamentals.refresh(db, ["MHHL"], date(2026, 11, 22), fetch)
    m = metrics(db, "MHHL")
    assert m["pe"] == approx(17.78, rel=1e-2)                     # market cap / latest net income
    assert m["roe"] == approx(0.0556, rel=1e-2)                   # 58.526 / 1053.258
    assert m["debt_to_equity"] == approx(0.328, rel=1e-2)        # 345.227 / 1053.258
    assert m["profit_cagr_3y"] == approx(0.0064, rel=5e-2)


def test_a_symbol_yahoo_does_not_know_is_skipped(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert fundamentals.refresh(db, ["NOSUCH"], date(2026, 11, 22), fetch) == {"stored": 0, "missing": ["NOSUCH"]}


def test_pool_is_liquid_stocks_plus_the_watchlist(tmp_path):
    from test_screen import AS_OF, series
    db = store.open(tmp_path / "sp.duckdb")
    series(db, "LIQUID", 0.001)                       # ₹3 cr a day
    series(db, "TINY", 0.001, value=2e5)              # ₹2 lakh a day
    series(db, "WATCHED", 0.001, value=2e5)
    db.execute("insert into watchlist (symbol, exchange, added_at) values ('WATCHED', 'NSE', ?)", [AS_OF])
    assert fundamentals.pool(db, AS_OF, liquidity_floor_cr=1.0) == ["LIQUID", "WATCHED"]
