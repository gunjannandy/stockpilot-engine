"""US share closes for Schedule FA (ServiceNow, `NOW`). Daily closes go into `prices` with exchange 'NYSE', one batch per run,
from the year of the first foreign lot. `fetch(symbols, start)` returns {symbol: [(date, open, high, low, close, volume)]}."""
from datetime import date

import duckdb

from stockpilot.book.kinds import FOREIGN_SQL


def symbols(db: duckdb.DuckDBPyConnection) -> list[str]:
    return [r[0] for r in db.execute(
        f"select distinct symbol from lots where {FOREIGN_SQL} order by symbol").fetchall()]


def first_year(db: duckdb.DuckDBPyConnection) -> int | None:
    row = db.execute(f"select min(year(acquired_on)) from lots where {FOREIGN_SQL}").fetchone()
    return row[0]


def refresh(db: duckdb.DuckDBPyConnection, fetch, as_of: date) -> int:
    names, year = symbols(db), first_year(db)
    if not names or year is None:
        return 0
    stored = 0
    for symbol, rows in fetch(names, date(year, 1, 1)).items():
        data = [(d, symbol, "NYSE", "EQ", o, h, l, c, None, int(v or 0), None, None)
                for d, o, h, l, c, v in rows if d <= as_of and c is not None]
        db.executemany("insert or replace into prices values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", data)
        stored += len(data)
    return stored


def yahoo_history(symbols_: list[str], start: date) -> dict:
    """The real fetcher: one yfinance download for every symbol. Imported lazily."""
    import yfinance as yf
    frame = yf.download(list(symbols_), start=start.isoformat(), auto_adjust=False, progress=False,
                        group_by="ticker", threads=False)
    out = {}
    for symbol in symbols_:
        sub = frame[symbol].dropna(subset=["Close"])
        out[symbol] = [(ts.date(), float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"]),
                        float(r.get("Volume") or 0)) for ts, r in sub.iterrows()]
    return out
