"""Daily and on-demand public data sources for the stock dossiers. Each module's `ingest` takes the
database, the day and a fetcher, stores what it finds and returns the rows stored; running it twice
for the same day leaves the same rows."""
from contextlib import contextmanager
from datetime import date, datetime


def nse_date(text: str | None) -> date | None:
    """NSE writes dates as 20-Nov-2026; a blank or '-' means none."""
    if not text or text.strip() in ("-", ""):
        return None
    return datetime.strptime(text.strip(), "%d-%b-%Y").date()


def number(text) -> float | None:
    """NSE writes numbers as text; '-' or null means none."""
    try:
        return float(str(text).replace(",", "").strip())
    except (TypeError, ValueError):
        return None


@contextmanager
def transaction(db):
    """One transaction: all of a source's rows for the day land together or not at all."""
    db.execute("begin")
    try:
        yield
    except BaseException:
        db.execute("rollback")
        raise
    db.execute("commit")


def insert(db, sql: str, rows: list) -> None:
    if rows:    # duckdb refuses an empty batch
        db.executemany(sql, rows)
