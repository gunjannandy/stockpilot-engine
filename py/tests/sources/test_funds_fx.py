import json
from datetime import date
from pathlib import Path

from stockpilot import store

from stockpilot.sources import funds, fx

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_navall_gives_each_scheme_its_category_house_and_nav(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    n = funds.ingest_navall(db, lambda url: (FIXTURES / "NAVAll.txt").read_bytes())
    assert n == 3
    row = db.execute("select name, plan, option, category, house from funds where scheme_code = 122639").fetchone()
    assert row == ("Parag Parikh Flexi Cap Fund", "Direct Plan", "Growth",
                   "Equity Scheme - Flexi Cap Fund", "PPFAS Mutual Fund")
    assert db.execute("select date, nav from navs where scheme_code = 122639").fetchone() == (date(2026, 11, 20), 95.4585)


def test_usd_inr_rate_for_a_day(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    body = json.dumps({"amount": 1.0, "base": "USD", "date": "2026-11-20", "rates": {"INR": 92.68}}).encode()
    assert fx.ingest_usdinr(db, date(2026, 11, 20), lambda url: body) == 92.68
    assert fx.usdinr_on(db, date(2026, 11, 22)) == 92.68     # weekend falls back to the last rate
