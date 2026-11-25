"""The results calendar: board meetings where results are due. Future rows and the last 90 days are kept."""
from datetime import date, timedelta

import duckdb

from stockpilot.sources import insert, nse_date, transaction

PATH = "/api/event-calendar?index=equities"
AHEAD_DAYS = 60        # the plain path lists only the next few days; the dated one is asked for first
KEEP_DAYS = 90


def _rows(day: date, fetch_json) -> list:
    """The next 60 days of results dates. If NSE refuses the dated request or answers nothing, the short list."""
    path = f"{PATH}&from_date={day:%d-%m-%Y}&to_date={day + timedelta(days=AHEAD_DAYS):%d-%m-%Y}"
    try:
        rows = fetch_json(path)
    except Exception:  # noqa: BLE001 - the short list still works; the readiness gap says how far dates reach
        rows = None
    return rows or fetch_json(PATH) or []


def ingest(db: duckdb.DuckDBPyConnection, day: date, fetch_json) -> int:
    floor = day - timedelta(days=KEEP_DAYS)
    rows = []
    for e in _rows(day, fetch_json):
        when = nse_date(e.get("date"))
        if e.get("symbol") and when and when >= floor:
            rows.append((e["symbol"], when, e.get("purpose") or "", e.get("bm_desc")))
    with transaction(db):
        insert(db, "insert or replace into results_calendar values (?, ?, ?, ?)", rows)
        db.execute("delete from results_calendar where date < ?", [floor])
    return len(rows)
