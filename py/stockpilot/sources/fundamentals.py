"""Fundamentals per stock, weekly. `fetch(symbol)` returns {"info": {...}, "income": {date: {...}},
"balance": {date: {...}}} or None; the yahoo() adapter below builds that shape from yfinance.
Ratios Yahoo leaves empty (common for small caps) are filled from the statements."""
import math
from datetime import date

import duckdb

INFO_MAP = {"trailingPE": "pe", "priceToBook": "pb", "returnOnEquity": "roe", "profitMargins": "profit_margin",
            "operatingMargins": "operating_margin", "marketCap": "market_cap", "heldPercentInsiders": "insiders_pct"}


def _ok(v):
    return v is not None and not (isinstance(v, float) and math.isnan(v))


def _by_year(table: dict) -> list[dict]:
    """Statement columns, newest first, skipping years Yahoo left empty."""
    return [table[k] for k in sorted(table, reverse=True) if any(_ok(v) for v in table[k].values())]


def _cagr(new, old, years):
    if _ok(new) and _ok(old) and new > 0 and old > 0:
        return (new / old) ** (1 / years) - 1
    return None


def compute(data: dict) -> dict[str, float]:
    info, inc, bal = data.get("info", {}), _by_year(data.get("income", {})), _by_year(data.get("balance", {}))
    m = {name: float(info[key]) for key, name in INFO_MAP.items() if _ok(info.get(key))}
    if _ok(info.get("debtToEquity")):
        m["debt_to_equity"] = info["debtToEquity"] / 100
    if inc and bal:
        ni, equity = inc[0].get("Net Income"), bal[0].get("Stockholders Equity")
        if "roe" not in m and _ok(ni) and _ok(equity) and equity > 0:
            m["roe"] = ni / equity
        if "debt_to_equity" not in m and _ok(bal[0].get("Total Debt")) and _ok(equity) and equity > 0:
            m["debt_to_equity"] = bal[0]["Total Debt"] / equity
        if "pe" not in m and _ok(info.get("marketCap")) and _ok(ni) and ni > 0:
            m["pe"] = info["marketCap"] / ni
        ebit, assets, cl = inc[0].get("EBIT"), bal[0].get("Total Assets"), bal[0].get("Current Liabilities")
        if _ok(ebit) and _ok(assets) and _ok(cl) and assets - cl > 0:
            m["roce"] = ebit / (assets - cl)
    if len(inc) >= 4:
        for key, name in (("Total Revenue", "revenue_cagr_3y"), ("Net Income", "profit_cagr_3y")):
            g = _cagr(inc[0].get(key), inc[3].get(key), 3)
            if g is not None:
                m[name] = g
    return m


def pool(db: duckdb.DuckDBPyConnection, as_of: date, liquidity_floor_cr: float = 1.0) -> list[str]:
    """The weekly batch: NSE stocks trading at least the floor a day over ~3 months, plus the watchlist."""
    rows = db.execute("""
        with recent as (
            select symbol, value, row_number() over (partition by symbol order by date desc) as rn
            from prices where exchange = 'NSE' and date <= ? and date > ? - interval 140 day)
        select symbol from recent where rn <= 63 group by symbol having avg(value) / 1e7 >= ?
        union select symbol from watchlist where removed_at is null
        order by symbol""", [as_of, as_of, liquidity_floor_cr]).fetchall()
    return [s for (s,) in rows]


def refresh(db: duckdb.DuckDBPyConnection, symbols: list[str], as_of: date, fetch) -> dict:
    stored, missing = 0, []
    for symbol in symbols:
        try:
            data = fetch(symbol)
        except Exception:  # one bad ticker must not stop the weekly batch
            data = None
        m = compute(data) if data else {}
        if not m:
            missing.append(symbol)
            continue
        db.executemany("insert or replace into fundamentals values (?, ?, ?, ?, 'yahoo')",
                       [(as_of, symbol, k, v) for k, v in m.items()])
        stored += 1
    return {"stored": stored, "missing": missing}


def yahoo(symbol: str, suffix: str = ".NS") -> dict | None:
    """yfinance adapter. Imported lazily: yfinance pulls in pandas, which only this job needs."""
    import yfinance as yf

    t = yf.Ticker(symbol + suffix)
    info = t.info or {}
    if not info or info.get("quoteType") is None and not info.get("marketCap"):
        return None

    def frame(df, rows):
        if df is None or df.empty:
            return {}
        return {str(c.date()): {r: (float(df.loc[r, c]) if _ok(df.loc[r, c]) else None) for r in rows if r in df.index}
                for c in df.columns}

    return {"info": {k: info.get(k) for k in [*INFO_MAP, "debtToEquity"]},
            "income": frame(t.income_stmt, ["Total Revenue", "Net Income", "EBIT"]),
            "balance": frame(t.balance_sheet, ["Total Assets", "Current Liabilities", "Total Debt", "Stockholders Equity"])}
