"""The stock list: names and ISINs for every NSE main-board and SME stock, with NSE's industry for
stocks in the Nifty Total Market index (others stay without one and are ranked against the whole pool)."""
import csv
import io

import duckdb

BASE = "https://nsearchives.nseindia.com"
EQUITY_L = BASE + "/content/equities/EQUITY_L.csv"
SME_L = BASE + "/emerge/corporates/content/SME_EQUITY_L.csv"
TOTAL_MARKET = BASE + "/content/indices/ind_niftytotalmarket_list.csv"


def _rows(blob):
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8-sig")))
    reader.fieldnames = [f.strip() for f in reader.fieldnames]
    return list(reader)


def refresh_stocks(db: duckdb.DuckDBPyConnection, fetch) -> int:
    stocks = {}
    for r in _rows(fetch(EQUITY_L)):
        stocks[r["SYMBOL"].strip()] = [r["NAME OF COMPANY"].strip(), None, r["ISIN NUMBER"].strip()]
    sme = fetch(SME_L)
    for r in _rows(sme) if sme else []:
        stocks[r["SYMBOL"].strip()] = [r["NAME_OF_COMPANY"].strip(), None, r["ISIN_NUMBER"].strip()]
    for r in _rows(fetch(TOTAL_MARKET)):
        if r["Symbol"].strip() in stocks:
            stocks[r["Symbol"].strip()][1] = r["Industry"].strip()
    db.execute("delete from stocks")
    db.executemany("insert into stocks values (?, ?, ?, ?)", [(s, *v) for s, v in stocks.items()])
    return len(stocks)
