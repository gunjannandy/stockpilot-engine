"""What the account holds and what each unit is worth today, in rupees. Reads the latest snapshot only."""
from datetime import date

import duckdb

from stockpilot.sources import fx
from stockpilot.book.kinds import canon

US_EXCHANGES = ("NYSE", "NASDAQ", "US")


def fund_for(db, isin: str | None):
    if not isin:
        return None
    return db.execute("select scheme_code, name, plan, option, category from funds "
                      "where isin_growth = ? or isin_reinvest = ?", [isin, isin]).fetchone()


def unit_price_inr(db: duckdb.DuckDBPyConnection, item: dict, as_of: date) -> float | None:
    kind = canon(item.get("kind"))
    if kind == "equity":
        row = db.execute("select close from prices where symbol = ? and date <= ? and exchange in ('NSE', 'BSE') "
                         "order by date desc, exchange desc limit 1", [item["symbol"], as_of]).fetchone()
        return row[0] if row else None
    if kind == "mf":
        fund = fund_for(db, item.get("isin"))
        row = fund and db.execute("select nav from navs where scheme_code = ? and date <= ? order by date desc limit 1",
                                  [fund[0], as_of]).fetchone()
        return row[0] if row else None
    if kind == "foreign":
        row = db.execute(f"select close from prices where symbol = ? and date <= ? and exchange in "
                         f"({','.join('?' * len(US_EXCHANGES))}) order by date desc limit 1",
                         [item["symbol"], as_of, *US_EXCHANGES]).fetchone()
        rate = fx.usdinr_on(db, as_of)
        return row[0] * rate if row and rate else None
    return None


def unit_prices_inr(db: duckdb.DuckDBPyConnection, items: list[dict], as_of: date, fund_codes: dict | None = None,
                    rate: float | None = None) -> list[float | None]:
    """`unit_price_inr` for many items in at most three queries (stocks, funds, US shares), however many there are.
    `fund_codes` maps an ISIN to its scheme code, and `rate` is the USD/INR rate, when the caller already has them."""
    out: list[float | None] = [None] * len(items)
    kinds = [canon(i.get("kind")) for i in items]
    equity = sorted({i["symbol"] for i, k in zip(items, kinds) if k == "equity"})
    price = dict(db.execute(
        "select symbol, close from prices where symbol in (select unnest(?)) and date <= ? and exchange in ('NSE', 'BSE') "
        "qualify row_number() over (partition by symbol order by date desc, exchange desc) = 1",
        [equity, as_of]).fetchall()) if equity else {}
    codes = {i.get("isin"): (fund_codes or {}).get(i.get("isin")) if fund_codes is not None else
             (fund_for(db, i.get("isin")) or [None])[0] for i, k in zip(items, kinds) if k == "mf" and i.get("isin")}
    wanted = sorted({c for c in codes.values() if c is not None})
    nav = dict(db.execute(
        "select scheme_code, nav from navs where scheme_code in (select unnest(?)) and date <= ? "
        "qualify row_number() over (partition by scheme_code order by date desc) = 1", [wanted, as_of]).fetchall()) if wanted else {}
    foreign = sorted({i["symbol"] for i, k in zip(items, kinds) if k == "foreign"})
    us = dict(db.execute(
        f"select symbol, close from prices where symbol in (select unnest(?)) and date <= ? and exchange in "
        f"({','.join('?' * len(US_EXCHANGES))}) qualify row_number() over (partition by symbol order by date desc) = 1",
        [foreign, as_of, *US_EXCHANGES]).fetchall()) if foreign else {}
    if foreign and rate is None:
        rate = fx.usdinr_on(db, as_of)
    for n, (item, kind) in enumerate(zip(items, kinds)):
        if kind == "equity":
            out[n] = price.get(item["symbol"])
        elif kind == "mf":
            code = codes.get(item.get("isin"))
            out[n] = nav.get(code) if code is not None else None
        elif kind == "foreign":
            close = us.get(item["symbol"])
            out[n] = close * rate if close is not None and rate else None
    return out
