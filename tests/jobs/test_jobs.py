import json
from datetime import date
from pathlib import Path

from stockpilot import store
from stockpilot.jobs import daily

FIXTURES = Path(__file__).parents[1] / "fixtures"
DOSSIER = FIXTURES / "dossier"
JSON = {"/api/holiday-master?type=trading": "nse_holidays.json", "/api/reportASM": "nse_asm.json",
        "/api/reportGSM": "nse_gsm.json",
        "/api/snapshot-capital-market-largedeal": "dossier/nse_bulk_block.json",
        "/api/event-calendar?index=equities": "dossier/nse_results_calendar.json",
        "/api/fiidiiTradeReact": "dossier/nse_fii_dii.json",
        "/api/corporates-financial-results?index=equities&period=Quarterly": "dossier/nse_financial_results.json"}


def fetch(url):
    if "frankfurter" in url:
        return b'{"amount":1.0,"base":"USD","date":"2026-11-20","rates":{"INR":92.68}}'
    name = url.rsplit("/", 1)[-1]
    path = DOSSIER / name if name.startswith("sec_bhavdata_full_") else FIXTURES / name
    return path.read_bytes() if path.exists() else None


def fetch_json(path):
    if path.startswith("/api/corporates-corporateActions"):
        return json.loads((FIXTURES / "nse_corporate_actions.json").read_text())
    if path.startswith("/api/corporate-announcements"):
        return json.loads((FIXTURES / "nse_announcements.json").read_text())
    return json.loads((FIXTURES / JSON[path]).read_text())


def test_daily_ingest_loads_every_source_and_records_the_run(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    report = daily.daily_ingest(db, date(2026, 11, 20), fetch, fetch_json)
    assert report["status"] == "ok"
    assert report["counts"] == {"nse_prices": 5, "bse_prices": 6, "indices": 4, "surveillance": 6,
                                "announcements": 3, "usdinr": 92.68, "corporate_actions": 2,
                                "delivery": 8, "deals": 10, "events": 5, "flows": 2, "filings": 5}
    assert db.execute("select job, status from runs").fetchall() == [("daily_ingest", "ok")]


def test_the_dossier_sources_are_stored_by_the_daily_ingest(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    daily.daily_ingest(db, date(2026, 11, 20), fetch, fetch_json)
    for table in ("delivery", "deals", "results_calendar", "flows", "filings_index"):
        assert db.execute(f"select count(*) from {table}").fetchone()[0] > 0, table


def test_a_failing_dossier_source_is_a_warning_and_the_run_is_partial(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")

    def broken(path):
        if "fiidii" in path:
            raise ConnectionError("NSE down")
        return fetch_json(path)

    report = daily.daily_ingest(db, date(2026, 11, 20), fetch, broken)
    assert report["status"] == "partial" and set(report["failed"]) == {"flows"}
    assert report["counts"]["deals"] == 10
    assert db.execute("select severity from problems").fetchall() == [("warning",)]


def test_a_holiday_is_skipped_without_fetching_prices(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    report = daily.daily_ingest(db, date(2026, 11, 24), fetch, fetch_json)
    assert report["status"] == "holiday"


def test_a_failing_source_is_recorded_as_a_problem_and_the_rest_still_run(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")

    def broken_bse(url):
        if "bseindia" in url:
            raise ConnectionError("BSE down")
        return fetch(url)

    report = daily.daily_ingest(db, date(2026, 11, 20), broken_bse, fetch_json)
    assert report["status"] == "partial"
    assert report["counts"]["nse_prices"] == 5
    assert "bse_prices" in report["failed"]
    assert db.execute("select job, severity from problems").fetchall() == [("daily_ingest", "warning")]
