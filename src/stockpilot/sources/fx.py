"""USD/INR from Frankfurter (ECB reference rates, free, no key)."""
import json
from datetime import date

import duckdb

URL = "https://api.frankfurter.dev/v1/{day}?from=USD&to=INR"


def ingest_usdinr(db: duckdb.DuckDBPyConnection, day: date, fetch) -> float:
    body = json.loads(fetch(URL.format(day=day.isoformat())))
    rate = float(body["rates"]["INR"])
    db.execute("insert or replace into fx values (?, 'USDINR', ?)", [date.fromisoformat(body["date"]), rate])
    return rate


def usdinr_on(db: duckdb.DuckDBPyConnection, day: date) -> float | None:
    row = db.execute("select rate from fx where pair = 'USDINR' and date <= ? order by date desc limit 1", [day]).fetchone()
    return row[0] if row else None


RANGE_URL = "https://api.frankfurter.dev/v1/{start}..{end}?from=USD&to=INR"


def ingest_usdinr_range(db: duckdb.DuckDBPyConnection, start: date, end: date, fetch) -> int:
    """One call for a whole window: Schedule FA needs a rate on every close in the calendar year."""
    body = json.loads(fetch(RANGE_URL.format(start=start.isoformat(), end=end.isoformat())))
    rows = [(date.fromisoformat(d), "USDINR", float(v["INR"])) for d, v in body.get("rates", {}).items()]
    db.executemany("insert or replace into fx values (?, ?, ?)", rows)
    return len(rows)


def _latest(db, pair: str, day: date):
    return db.execute("select date, rate from fx where pair = ? and date <= ? order by date desc limit 1", [pair, day]).fetchone()


def rate_on(db):
    """USD/INR for a day. The SBI TT buying rate (pair USDINR_SBI, supplied by the owner) wins where it exists;
    Frankfurter (ECB) is the documented fallback."""
    def get(day: date):
        sbi = _latest(db, "USDINR_SBI", day)
        return sbi[1] if sbi else usdinr_on(db, day)
    return get


def source_note(db, day: date) -> str:
    return "SBI TT buying rate" if _latest(db, "USDINR_SBI", day) else "Frankfurter (ECB reference rate, the fallback)"
