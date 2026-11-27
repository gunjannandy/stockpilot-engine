"""Bulk and block deals: large trades NSE names the buyer or seller of. Short-selling rows are not kept."""
from datetime import date

import duckdb

from stockpilot.sources import insert, nse_date, number, transaction

PATH = "/api/snapshot-capital-market-largedeal"
KEYS = {"bulk": "BULK_DEALS_DATA", "block": "BLOCK_DEALS_DATA"}


def ingest(db: duckdb.DuckDBPyConnection, day: date, fetch_json) -> int:
    data = fetch_json(PATH) or {}
    rows = []
    for kind, key in KEYS.items():
        for d in data.get(key) or []:
            when, qty = nse_date(d.get("date")) or day, number(d.get("qty"))
            if not d.get("symbol") or qty is None:
                continue
            rows.append((when, d["symbol"], kind, d.get("clientName"), d.get("buySell"), int(qty), number(d.get("watp"))))
    with transaction(db):
        for when in {r[0] for r in rows}:    # a day's deals are replaced as a whole
            db.execute("delete from deals where date = ?", [when])
        insert(db, "insert into deals values (?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows)
