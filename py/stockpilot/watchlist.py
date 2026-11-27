"""The owners' watchlist: symbols always analysed, edited from the dashboard. Removal is soft, so undo is an add."""
import csv
from pathlib import Path

import duckdb


def active(db: duckdb.DuckDBPyConnection) -> list[tuple[str, str]]:
    return db.execute("select symbol, exchange from watchlist where removed_at is null "
                      "order by symbol, exchange").fetchall()


def add(db, symbol: str, exchange: str, by: str) -> bool:
    if (symbol, exchange) in active(db):
        return False
    db.execute("insert into watchlist (symbol, exchange, added_by) values (?, ?, ?)", [symbol, exchange, by])
    return True


def remove(db, symbol: str, exchange: str, by: str) -> bool:
    n = db.execute("update watchlist set removed_at = current_timestamp where symbol = ? and exchange = ? "
                   "and removed_at is null returning 1", [symbol, exchange]).fetchall()
    return bool(n)


def import_csv(db, path: Path | str) -> int:
    with open(path, newline="") as f:
        return sum(add(db, r["symbol"].strip(), r["exchange"].strip(), by=f"import:{r.get('source', '')}")
                   for r in csv.DictReader(f))
