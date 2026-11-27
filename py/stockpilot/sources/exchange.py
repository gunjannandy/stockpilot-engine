"""Exchange calendar and surveillance lists, from the NSE JSON API through `fetch_json(path)`."""
from datetime import date, datetime

import duckdb


def refresh_holidays(db: duckdb.DuckDBPyConnection, fetch_json) -> int:
    rows = [(datetime.strptime(h["tradingDate"], "%d-%b-%Y").date(), h["description"])
            for h in fetch_json("/api/holiday-master?type=trading")["CM"]]
    db.executemany("insert or replace into holidays values (?, ?)", rows)
    return len(rows)


def is_trading_day(db: duckdb.DuckDBPyConnection, day: date) -> bool:
    if day.weekday() >= 5:
        return False
    return db.execute("select count(*) from holidays where date = ?", [day]).fetchone()[0] == 0


def refresh_surveillance(db: duckdb.DuckDBPyConnection, as_of: date, fetch_json) -> dict[str, str]:
    """Store today's ASM and GSM lists; returns symbol -> label (first listing wins)."""
    flagged: dict[str, str] = {}
    asm = fetch_json("/api/reportASM")
    for term, prefix in (("longterm", "LTASM"), ("shortterm", "STASM")):
        for item in asm.get(term, {}).get("data", []):
            flagged.setdefault(item["symbol"], f"{prefix} {item['asmSurvIndicator']}")
    for item in fetch_json("/api/reportGSM"):
        flagged.setdefault(item["symbol"], f"GSM {item['gsmStage']}")
    db.execute("delete from surveillance where as_of = ?", [as_of])
    db.executemany("insert into surveillance values (?, ?, ?)", [(as_of, s, l) for s, l in flagged.items()])
    return flagged

