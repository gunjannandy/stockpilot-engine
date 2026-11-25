"""AMFI's TER page is a JSON API (checked on the VM 2026-11-25): per fund house and month, Regular and Direct cost for every scheme."""
import json
from datetime import date

from stockpilot import store
from stockpilot.sources import fundcosts


def row(name, r, d, cat="Equity Schemes - Flexi Cap Fund"):
    return {"Scheme_Name": name, "SchemeCat_Desc": cat, "R_TER": r, "D_TER": d, "MF_ID": 7, "Month": "11-2026"}


def page(rows, n=None):
    return json.dumps({"data": rows, "meta": {"total": n if n is not None else len(rows)}}).encode()


def test_ter_rows_are_keyed_like_the_funds_and_zero_means_unknown():
    got = fundcosts.parse_ter_api([row("Parag Parikh Flexi Cap Fund", "1.3500", "0.6300"), row("Odd Fund", "0.0000", "")])
    assert got[fundcosts.scheme_key("Parag Parikh Flexi Cap Fund")] == (1.35, 0.63)
    assert got[fundcosts.scheme_key("Odd Fund")] == (None, None)


def test_refresh_reads_every_page_of_every_house_and_stores_the_month(tmp_path):
    db = store.open(tmp_path / "t.duckdb", job="test")
    calls = []

    def fetch(url):
        calls.append(url)
        if "MF_ID=1&" in url:
            return page([row("A Fund", "1.0", "0.5"), row("B Fund", "2.0", "1.0")], n=3) if "page=1&" in url else page([row("C Fund", "1.5", "0.7")], n=3)
        return page([])
    stored = fundcosts.refresh_api(db, date(2026, 11, 25), fetch, mf_ids=[1, 2], page_size=2)
    assert stored == 3
    assert db.execute("select ter_direct from fund_costs where key = ?", [fundcosts.scheme_key("C Fund")]).fetchone()[0] == 0.7
    assert any("Month=11-2026" in u for u in calls)


def test_a_house_that_fails_is_skipped_not_fatal(tmp_path):
    db = store.open(tmp_path / "t.duckdb", job="test")
    fetch = lambda url: None if "MF_ID=1&" in url else page([row("Z Fund", "1.0", "0.4")])   # noqa: E731
    assert fundcosts.refresh_api(db, date(2026, 11, 25), fetch, mf_ids=[1, 2]) == 1


def test_an_empty_new_month_falls_back_to_last_month(tmp_path):
    db = store.open(tmp_path / "t.duckdb", job="test")
    fetch = lambda url: page([row("Old Fund", "1.0", "0.5")]) if "Month=10-2026" in url else page([])   # noqa: E731
    assert fundcosts.refresh_api(db, date(2026, 11, 3), fetch, mf_ids=[1]) == 1
    assert db.execute("select as_of from fund_costs").fetchone()[0] == date(2026, 10, 1)
