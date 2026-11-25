import json
from datetime import date, timedelta

import pytest

from helpers import insert_prices
from stockpilot import store, valuation, weekly
from stockpilot.analysis import allocation, fundreview, opportunities

AS_OF = date(2026, 11, 21)   # a Saturday


def _fund(db, code, name, nav_now, nav_3y, category="Equity Scheme - Flexi Cap Fund", plan="Direct Plan",
          option="Growth", nav_1y=None):
    db.execute("insert into funds values (?, ?, null, ?, ?, ?, ?, 'House')", [code, f"INF{code}", name, plan, option, category])
    db.execute("insert into navs values (?, ?, ?)", [AS_OF, code, nav_now])
    db.execute("insert into navs values (?, ?, ?)", [AS_OF - timedelta(days=365), code, nav_1y or (nav_now + nav_3y) / 2])
    db.execute("insert into navs values (?, ?, ?)", [AS_OF - timedelta(days=3 * 365), code, nav_3y])


def _peers(db):
    for code, now in zip(range(1, 6), (100, 120, 140, 160, 180)):
        _fund(db, code, f"Fund {code}", now, 100)


def _hold(db, kind, symbol, isin, qty, avg=0.0):
    db.execute("insert into holdings values (?, ?, ?, ?, ?, ?, 'test')", [AS_OF, kind, symbol, isin, qty, avg])


def test_fund_review_ranks_a_held_fund_against_its_category(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    _peers(db)
    _hold(db, "mf", "Fund 1", "INF1", 100)
    _hold(db, "mf", "Fund 4", "INF4", 100)
    rows = {r["name"]: r for r in fundreview.review(db, AS_OF)}
    assert rows["Fund 1"]["verdict"] == "Review" and rows["Fund 1"]["rank"] == (5, 5)
    assert rows["Fund 1"]["better_peer"] == "Fund 5"
    assert rows["Fund 4"]["verdict"] == "Keep" and rows["Fund 4"]["better_peer"] is None
    assert "bottom" in rows["Fund 1"]["why"]


def test_fund_review_says_so_when_history_or_peers_are_missing(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    _fund(db, 9, "Lonely Fund", 120, 100)
    _hold(db, "mf", "Lonely Fund", "INF9", 10)
    [row] = fundreview.review(db, AS_OF)
    assert row["verdict"] == "Too early to judge" and "peers" in row["why"]


def test_allocation_shows_gap_to_target_in_rupees(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    insert_prices(db, [(AS_OF, "ABC", "NSE", "EQ", 200, 200, 200, 200, 200, 1, 1, 1),
                       (AS_OF, "NOW", "NYSE", "", 100, 100, 100, 100, 100, 1, 1, 1)])
    db.execute("insert into fx values (?, 'USDINR', 90)", [AS_OF])
    _fund(db, 1, "Fund 1", 50, 40)
    _hold(db, "equity", "ABC", "INE-ABC", 100)
    _hold(db, "mf", "Fund 1", "INF1", 400)
    _hold(db, "foreign", "NOW", "US81762P1021", 2)
    out = allocation.compare(db, AS_OF, {"stocks": 0.5, "equity_funds": 0.3, "foreign": 0.2})
    assert out["total"] == 58_000
    by = {r["class"]: r for r in out["rows"]}
    assert by["stocks"]["value"] == 20_000 and by["foreign"]["value"] == 18_000
    assert by["stocks"]["gap_inr"] == 9_000 and "Add" in by["stocks"]["action"]
    assert by["foreign"]["gap_inr"] == pytest.approx(-6_400) and "Trim" in by["foreign"]["action"]


def test_allocation_without_a_target_still_reports_what_is_held(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    insert_prices(db, [(AS_OF, "ABC", "NSE", "EQ", 200, 200, 200, 200, 200, 1, 1, 1)])
    _hold(db, "equity", "ABC", "INE-ABC", 10)
    out = allocation.compare(db, AS_OF, None)
    assert out["target_set"] is False and out["rows"][0]["share"] == 1.0


def test_opportunities_skip_what_is_held_and_flagged_names():
    cands = [{"symbol": s, "composite": c, "flags": f, "scores": {"quality": q, "value": 0.4, "momentum": 0.5, "risk": 0.5},
              "industry": "Banks", "exchange": "NSE", "watchlist": False}
             for s, c, f, q in (("A", .9, [], .95), ("B", .8, [], .5), ("C", .7, ["illiquid"], .5), ("D", .6, [], .5))]
    picks = opportunities.pick(cands, held={"A"}, n=2)
    assert [p["symbol"] for p in picks] == ["B", "D"]
    assert picks[0]["why"]


def test_valuation_prices_each_kind_in_rupees(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    insert_prices(db, [(AS_OF, "ABC", "NSE", "EQ", 200, 200, 200, 200, 200, 1, 1, 1)])
    assert valuation.unit_price_inr(db, {"kind": "equity", "symbol": "ABC", "isin": "x"}, AS_OF) == 200
    assert valuation.unit_price_inr(db, {"kind": "equity", "symbol": "ZZZ", "isin": "x"}, AS_OF) is None


def test_weekly_runs_every_section_on_a_seeded_db_and_stores_the_report(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    _peers(db)
    insert_prices(db, [(AS_OF, "ABC", "NSE", "EQ", 200, 200, 200, 200, 200, 1, 1, 1)])
    _hold(db, "equity", "ABC", "INE-ABC", 100)
    db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, source) values "
               "('equity', 'ABC', 'INE-ABC', '2024-01-01', 100, 100, 'test')")
    db.execute("insert into sales (kind, symbol, isin, sold_on, quantity, price_per_unit, currency, expenses) values "
               "('equity', 'ABC', 'INE-ABC', '2026-06-01', 40, 150, 'INR', 0)")
    result = weekly.run(db, AS_OF, tmp_path / "tax", target={"stocks": 1.0})
    assert result["status"] == "ok", result
    sections = dict(db.execute("select section, payload from weekly_reports where week_of = ?", [AS_OF]).fetchall())
    assert set(sections) == {"funds", "opportunities", "allocation", "tax", "gaps"}
    tax_payload = json.loads(sections["tax"])
    assert tax_payload["fy"] == "2026-27" and tax_payload["ltcg_equity"] == 2_000
    assert (tmp_path / "tax" / "2026-27" / "summary.json").exists()
    assert db.execute("select status from runs where job = 'weekly'").fetchone()[0] == "ok"


def test_one_failing_section_does_not_stop_the_others(tmp_path, monkeypatch):
    db = store.open(tmp_path / "sp.duckdb")
    monkeypatch.setattr(fundreview, "review", lambda *a, **k: 1 / 0)
    result = weekly.run(db, AS_OF, tmp_path / "tax", target=None)
    assert result["status"] == "partial" and "funds" in result["failed"]
    assert db.execute("select count(*) from problems where job = 'weekly'").fetchone()[0] == 1
    assert db.execute("select count(*) from weekly_reports where section = 'allocation'").fetchone()[0] == 1


def test_sales_with_no_matching_lot_is_a_problem_not_a_wrong_number(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    db.execute("insert into sales (kind, symbol, isin, sold_on, quantity, price_per_unit, currency, expenses) values "
               "('equity', 'ABC', 'INE-ABC', '2026-06-01', 40, 150, 'INR', 0)")
    result = weekly.run(db, AS_OF, tmp_path / "tax", target=None)
    assert "tax" in result["failed"] and "ABC" in result["failed"]["tax"]
