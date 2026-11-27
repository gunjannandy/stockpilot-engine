"""FII and DII money flows. NSE answers for the latest day only, so history builds up one day at a time."""
from datetime import date

import duckdb

from stockpilot.sources import insert, nse_date, number

PATH = "/api/fiidiiTradeReact"
CATEGORY = {"FII/FPI": "FII", "FII": "FII", "DII": "DII"}


def ingest(db: duckdb.DuckDBPyConnection, day: date, fetch_json) -> int:
    rows = []
    for f in fetch_json(PATH) or []:
        category = CATEGORY.get((f.get("category") or "").strip())
        buy, sell, net = number(f.get("buyValue")), number(f.get("sellValue")), number(f.get("netValue"))
        if category and net is not None:
            rows.append((nse_date(f.get("date")) or day, category, buy, sell, net))
    insert(db, "insert or replace into flows values (?, ?, ?, ?, ?)", rows)
    return len(rows)
