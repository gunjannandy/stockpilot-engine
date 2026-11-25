"""Adapters that turn public NSE and yfinance data into dated `facts.Record`s, plus the job that publishes the files.
The NSE field names below follow NSE's own filings and web API; NSE changes them without notice, so every parser skips
what it cannot read instead of guessing, and the daily coverage report shows when a source goes quiet."""
import re
import xml.etree.ElementTree as ET
from datetime import date, datetime
from pathlib import Path

from stockpilot.sources import facts as F

# XBRL element (local name) -> metric. First match for a metric wins. Flows need the full-year context, stocks the year-end one.
XBRL_FLOWS = {"RevenueFromOperations": "sales", "ProfitLossForPeriod": "profit", "ProfitBeforeTax": "pbt",
              "FinanceCosts": "finance_costs"}
XBRL_STOCKS = {"Equity": "equity", "Borrowings": "debt", "Assets": "assets", "CurrentLiabilities": "current_liabilities"}
SCALE_TO_CRORE = {"actual": 1e-7, "rupees": 1e-7, "thousands": 1e-4, "lakhs": 1e-2, "lakh": 1e-2, "millions": 0.1, "crores": 1.0, "crore": 1.0}


def _local(tag):
    return tag.rsplit("}", 1)[-1]


def _day(text):
    for fmt in ("%d-%b-%Y %H:%M:%S", "%d-%b-%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _num(text):
    try:
        return float(str(text).replace(",", ""))
    except (TypeError, ValueError):
        return None


def parse_xbrl(blob: bytes, period_end: date, available_on: date) -> list[F.Record]:
    try:
        root = ET.fromstring(blob)
    except ET.ParseError:
        return []
    ctx = {}                                   # id -> (start or None, end)
    for c in root.iter():
        if _local(c.tag) == "context":
            p = {_local(e.tag): (e.text or "").strip() for e in c.iter()}
            end = _day(p.get("endDate") or p.get("instant") or "")
            ctx[c.get("id")] = (_day(p["startDate"]) if p.get("startDate") else None, end)
    scale = 1e-2                                # NSE files are in lakhs unless they say otherwise
    for e in root.iter():
        if _local(e.tag) in ("ScaleOfFigures", "LevelOfRoundingUsedInFinancialStatements") and e.text:
            scale = next((v for k, v in SCALE_TO_CRORE.items() if k in e.text.lower()), scale)
    best: dict[str, tuple[int, float]] = {}     # metric -> (duration days, value)
    for e in root.iter():
        name, c = _local(e.tag), ctx.get(e.get("contextRef"))
        val = _num(e.text)
        if c is None or val is None or c[1] != period_end:
            continue
        if name in XBRL_FLOWS and c[0]:
            days = (c[1] - c[0]).days
            if days >= 300 and days >= best.get(XBRL_FLOWS[name], (0, 0))[0]:
                best[XBRL_FLOWS[name]] = (days, val)
        elif name in XBRL_STOCKS and c[0] is None:
            best.setdefault(XBRL_STOCKS[name], (0, val))
    recs = [F.Record(m, round(v * scale, 2), period_end, available_on, "nse") for m, (_, v) in best.items()]
    by = {r.metric: r.value for r in recs}
    if "pbt" in by and "finance_costs" in by:
        recs.append(F.Record("ebit", round(by["pbt"] + by["finance_costs"], 2), period_end, available_on, "nse"))
    if "assets" in by and "current_liabilities" in by:
        recs.append(F.Record("capital_employed", round(by["assets"] - by["current_liabilities"], 2), period_end, available_on, "nse"))
    return [r for r in recs if r.metric not in ("pbt", "finance_costs", "assets", "current_liabilities")]


def _rows(rows, field_candidates, metric):
    out = []
    for r in rows:
        value = next((_num(r[k]) for k in field_candidates if k in r and _num(r[k]) is not None), None)
        period = _day(r.get("date", ""))
        avail = next((_day(r[k]) for k in ("submissionDate", "broadcastDate", "systemDate") if r.get(k) and _day(r[k])), None)
        if value is not None and period and avail:        # no filing date, no use: it could be look-ahead
            out.append(F.Record(metric, value, period, avail, "nse"))
    return out


def parse_shareholding(rows):
    return _rows(rows, ("pr_and_prgrp", "promoterAndPromoterGroup"), "promoter_pct")


def parse_pledge(rows):
    return _rows(rows, ("percSharesPledged", "percPromoterSharesEncumbered"), "pledge_pct")


def from_yfinance(info: dict, fetched_on: date) -> list[F.Record]:
    def num(k):
        v = info.get(k)
        return float(v) if isinstance(v, (int, float)) and v == v else None
    pick = {"pe": ("trailingPE", 1), "pb": ("priceToBook", 1), "roe_pct": ("returnOnEquity", 100),
            "debt_to_equity": ("debtToEquity", 0.01), "market_cap_cr": ("marketCap", 1e-7),
            "dividend_yield_pct": ("dividendYield", 1), "promoter_pct": ("heldPercentInsiders", 100)}
    return [F.Record(m, round(num(k) * mult, 2), fetched_on, fetched_on, "yfinance")
            for m, (k, mult) in pick.items() if num(k) is not None]


def run(universe: list[dict], gather, prices: dict[str, float], out: Path, today: date) -> dict:
    """universe: [{symbol, exchange, name, sector}]. gather(symbol) -> [Record]; one failing symbol is reported, not fatal."""
    docs, failed = {}, []
    for u in universe:
        try:
            recs = gather(u["symbol"])
        except Exception:
            failed.append(u["symbol"])
            continue
        if recs:
            docs[u["symbol"]] = F.build_facts(u["symbol"], u["exchange"], u["name"], u["sector"], recs, today,
                                              prices.get(u["symbol"]))
    F.add_sector_pe(docs)
    cov = F.coverage(docs, [u["symbol"] for u in universe])
    cov["failed"] = failed
    cov["as_of"] = today.isoformat()
    F.write_all(docs, cov, out)
    return cov


def live_gather(session, fetch, yf_info, today: date):
    """The real-run gatherer: NSE results (XBRL), shareholding and pledge through one cookie session, then yfinance for gaps."""
    def gather(symbol):
        recs = []
        for path, parse in ((f"/api/corporate-share-holdings-master?index=equities&symbol={symbol}", parse_shareholding),
                            (f"/api/corporate-pledgedata?index=equities&symbol={symbol}", parse_pledge)):
            try:
                recs += parse(session.fetch_json(path) or [])
            except Exception:
                pass
        try:
            for r in (session.fetch_json(f"/api/corporates-financial-results?index=equities&symbol={symbol}&period=Annual") or [])[:11]:
                end, avail, url = _day(r.get("toDate", "")), _day(r.get("broadcastDate") or r.get("filingDate") or ""), r.get("xbrl")
                if end and avail and url and url != "-":
                    recs += parse_xbrl(fetch(url) or b"", end, avail)
        except Exception:
            pass
        try:
            recs += from_yfinance(yf_info(symbol), today)
        except Exception:
            pass
        return recs
    return gather


def main(argv=None):
    """python -m stockpilot.sources.facts_sources SEARCH_INDEX.json OUT_DIR [LIMIT]: the public weekly job's entry point."""
    import json
    import sys
    from stockpilot.sources.http import fetch
    from stockpilot.sources.nse_api import Session
    a = argv or sys.argv[1:]
    index = json.loads(Path(a[0]).read_text())["entries"]
    universe = [{"symbol": e["symbol"], "exchange": e["exchange"], "name": e["name"], "sector": ""} for e in index
                if e["segment"] in ("NSE", "NSE_SME")][: int(a[2]) if len(a) > 2 else None]
    import yfinance as yf
    cache = {}

    def yf_info(symbol):
        cache[symbol] = yf.Ticker(symbol + ".NS").info
        return cache[symbol]
    today = date.today()
    gather = live_gather(Session(), fetch, yf_info, today)
    prices = {}
    by_symbol = {u["symbol"]: u for u in universe}

    def gather_and_price(symbol):
        recs = gather(symbol)
        info = cache.pop(symbol, {})
        px = info.get("currentPrice")
        by_symbol[symbol]["sector"] = info.get("sector") or ""
        if px:
            prices[symbol] = float(px)
        return recs
    cov = run(universe, gather_and_price, prices, Path(a[1]), today)
    print(f"facts: {cov['with_facts']}/{cov['universe']} stocks; failed {len(cov['failed'])}; "
          + ", ".join(f"{k} {v['pct']}%" for k, v in cov["metrics"].items()))


if __name__ == "__main__":
    main()
