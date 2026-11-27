"""Delivery %: the share of each day's traded shares that were taken home, from NSE's full bhavcopy."""
import csv
import io
from datetime import date

import duckdb

from stockpilot.sources import insert, number, transaction

URL = "https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{day:%d%m%Y}.csv"
SERIES = {"EQ", "BE"}


def ingest(db: duckdb.DuckDBPyConnection, day: date, fetch) -> int:
    blob = fetch(URL.format(day=day))
    if not blob:
        return 0
    rows = []
    for rec in csv.DictReader(io.StringIO(blob.decode("utf-8-sig"))):
        rec = {k.strip(): (v or "").strip() for k, v in rec.items() if k}
        if rec.get("SERIES") not in SERIES or not rec.get("SYMBOL"):
            continue
        qty, pct = number(rec.get("DELIV_QTY")), number(rec.get("DELIV_PER"))
        rows.append((day, rec["SYMBOL"], rec["SERIES"], None if qty is None else int(qty), pct))
    with transaction(db):
        db.execute("delete from delivery where date = ?", [day])
        insert(db, "insert or replace into delivery values (?, ?, ?, ?, ?)", rows)
    return len(rows)
