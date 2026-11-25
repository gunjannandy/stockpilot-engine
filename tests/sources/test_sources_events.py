import json
from datetime import date
from pathlib import Path

from stockpilot import store
from stockpilot.sources import events

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "dossier" / "nse_results_calendar.json").read_text())
DAY = date(2026, 11, 20)


def test_events_store_the_results_calendar(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    paths = []

    def fetch_json(path):
        paths.append(path)
        return FIXTURE

    assert events.ingest(db, DAY, fetch_json) == 5
    assert paths == ["/api/event-calendar?index=equities&from_date=20-11-2026&to_date=19-01-2027"]
    assert db.execute("select date, purpose, detail from results_calendar where symbol = 'HEADSUP'").fetchone() == (
        date(2026, 11, 24), "Financial Results",
        "To consider and approve the financial results for the period ended September 30, 2026")


def test_events_are_idempotent_and_keep_future_and_last_90_days_only(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    old = {"symbol": "OLDCO", "purpose": "Financial Results", "bm_desc": "x", "date": "01-Jan-2026"}
    recent = {"symbol": "RECENT", "purpose": "Financial Results", "bm_desc": "y", "date": "01-Oct-2026"}
    events.ingest(db, DAY, lambda p: FIXTURE + [old, recent])
    events.ingest(db, DAY, lambda p: FIXTURE + [old, recent])
    symbols = {s for (s,) in db.execute("select symbol from results_calendar").fetchall()}
    assert "OLDCO" not in symbols and "RECENT" in symbols
    assert db.execute("select count(*) from results_calendar").fetchone()[0] == 6


def test_a_row_stored_earlier_survives_a_later_feed_that_no_longer_lists_it(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    events.ingest(db, DAY, lambda p: FIXTURE)
    events.ingest(db, date(2026, 11, 25), lambda p: FIXTURE[:1])
    assert db.execute("select count(*) from results_calendar").fetchone()[0] == 5
    events.ingest(db, date(2027, 6, 1), lambda p: [])   # all now older than 90 days
    assert db.execute("select count(*) from results_calendar").fetchone()[0] == 0
