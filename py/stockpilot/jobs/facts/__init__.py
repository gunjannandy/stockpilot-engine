"""The facts Job: each stock's valuation and quality metrics, the sector comparison, plain sentences in English and
Bengali, and the raw figures behind them (value, period, source). NSE XBRL filings first, yfinance only for gaps.

Public data only. Published as the `facts` dataset, one row per stock; a stock whose sources give nothing is left
out and the run goes on. The Stock page reads it through the Worker's /api/facts route."""
import json
from collections.abc import Callable
from datetime import date

from stockpilot.sources import facts as F

from .templates import render

KIND = DATASET = "facts"
METRICS = (*F.VALUATION_KEYS, *F.QUALITY_KEYS)
FIGURE_KEYS = ("sales", "profit", "ebit", "equity", "debt", "capital_employed", "shares", *F.QUALITY_KEYS[-2:],
               "pe", "pb", "roe_pct", "debt_to_equity", "market_cap_cr", "dividend_yield_pct")


def sentences(v: dict, q: dict) -> list[dict]:
    s = []
    if v.get("pe") is not None:
        s.append(render("pe", pe=f"{v['pe']:.0f}"))
        if v.get("pe_sector") is not None:
            s.append(render("pe_cheaper" if v["pe"] < v["pe_sector"] else "pe_dearer", pe_sector=f"{v['pe_sector']:.0f}"))
    for key, up, down in (("sales_growth_yoy_pct", "sales_up", "sales_down"), ("profit_growth_yoy_pct", "profit_up", "profit_down")):
        g = q.get(key)
        if g is not None:
            s.append(render(up if g >= 0 else down, pct=f"{abs(g):.0f}"))
    if q.get("roe_pct") is not None:
        s.append(render("roe", roe=f"{q['roe_pct']:.0f}"))
    d = q.get("debt_to_equity")
    if d is not None:
        s.append(render("debt_low") if d < 0.3 else render("debt", debt=f"{d:.1f}"))
    if q.get("promoter_pct") is not None:
        s.append(render("promoter", promoter=f"{q['promoter_pct']:.0f}"))
    p = q.get("pledge_pct")
    if p is not None:
        s.append(render("pledge_none") if p == 0 else render("pledge", pledge=f"{p:.0f}"))
    return s


def price_sentences(rows: list[dict]) -> list[dict]:
    """Sentences from daily history rows ({close, volume}, oldest first): biggest fall, daily swing, trading."""
    closes = [r["close"] for r in rows if r.get("close")]
    out = []
    if len(closes) < 60:
        return out
    peak, fall = closes[0], 0.0
    for c in closes:
        peak = max(peak, c)
        fall = min(fall, c / peak - 1)
    moves = [abs(b / a - 1) * 100 for a, b in zip(closes, closes[1:])]
    out.append(render("biggest_fall", fall=f"{abs(fall) * 100:.0f}"))
    out.append(render("swings", swing=f"{sum(moves) / len(moves):.1f}"))
    vols = sorted(r["volume"] for r in rows if r.get("volume"))
    if vols:
        out.append(render("trading", volume=f"{int(vols[len(vols) // 2]):,}"))
    return out


def figures(records, day: date) -> list[dict]:
    """The newest figure of each metric (a filing beats yfinance), with its period and source, in a fixed order."""
    rec = F.as_of(records, day)
    out = []
    for m in dict.fromkeys(FIGURE_KEYS):
        r = F._latest(rec, m)
        if r:
            out.append({"metric": m, "value": r.value, "period": r.period_end.isoformat(), "source": r.source})
    return out


def similar(doc: dict, docs: dict[str, dict], limit: int = 5) -> list[str]:
    """Symbols of up to `limit` other stocks of the same sector, nearest by market cap (no sector, no list)."""
    if not doc.get("sector") or doc["valuation"].get("market_cap_cr") is None:
        return []
    cap = doc["valuation"]["market_cap_cr"]
    peers = [d for d in docs.values() if d["symbol"] != doc["symbol"] and d.get("sector") == doc["sector"]
             and d["valuation"].get("market_cap_cr") is not None]
    peers.sort(key=lambda d: (abs(d["valuation"]["market_cap_cr"] - cap), d["symbol"]))
    return [d["symbol"] for d in peers[:limit]]


def row(doc: dict, records, day: date, history: list[dict] | None = None, similar_symbols: list[str] | None = None) -> dict:
    v, q = doc["valuation"], doc["quality"]
    s = sentences(v, q) + price_sentences(history or [])
    return {"id": f"{doc['exchange']}:{doc['symbol']}", "symbol": doc["symbol"], "exchange": doc["exchange"],
            "name": doc.get("name") or "", "sector": doc.get("sector") or "", "as_of": day.isoformat(),
            **{k: v.get(k) for k in F.VALUATION_KEYS if k != "pe_own_5y_median"},
            **{k: q.get(k) for k in F.QUALITY_KEYS},
            "sentences_json": json.dumps(s, ensure_ascii=False, separators=(",", ":")),
            "figures_json": json.dumps(figures(records, day), separators=(",", ":")),
            "similar_json": json.dumps(similar_symbols or [], separators=(",", ":")),
            "not_available": "|".join(doc["not_available"])}


def collect(universe: list[dict], gather: Callable[[str], list], prices: dict[str, float], day: date,
            progress: Callable[[str], None] = lambda _: None,
            history: Callable[[str], list[dict]] | None = None) -> list[dict]:
    """universe: [{symbol, exchange, name, sector}]. One failing symbol is reported, not fatal."""
    docs, recs, failed = {}, {}, []
    for u in universe:
        try:
            r = gather(u["symbol"])
        except Exception:  # noqa: BLE001 - one stock failing leaves only that stock out
            failed.append(u["symbol"])
            continue
        if r:
            recs[u["symbol"]] = r
            docs[u["symbol"]] = F.build_facts(u["symbol"], u["exchange"], u["name"], u["sector"], r, day, prices.get(u["symbol"]))
    F.add_sector_pe(docs)
    progress(f"{len(docs)} of {len(universe)} stocks with facts, {len(failed)} failed")
    out = []
    for s, d in docs.items():
        try:
            h = history(s) if history else []
        except Exception:  # noqa: BLE001 - no history only drops the price sentences
            h = []
        r = row(d, recs[s], day, h, similar(d, docs))
        if r["figures_json"] == "[]":  # the door holds back a row with no raw figure; too many fail the whole run
            continue
        out.append(r)
    progress(f"{len(out)} stocks with at least one figure")
    return out


def run(ctx, universe: list[dict] | None = None, gather=None, prices: dict | None = None) -> str:
    day = ctx.range.end
    if universe is None:
        rows = ctx.client._ok("/api/stocks/universe", None, "GET").get("rows", [])
        universe = [{"symbol": r["symbol"], "exchange": r["exchange"], "name": r["name"], "sector": ""} for r in rows
                    if r["status"] == "listed" and r["segment"] in ("NSE", "NSE_SME")]
        if ctx.subject not in ("all", "facts"):  # one stock: the load on demand asks for it
            universe = [u for u in universe if u["symbol"] == ctx.subject]
    if gather is None:
        gather, prices = _live(universe, day)
    out = collect(universe, gather, prices or {}, day, ctx.progress.line,
                  lambda sym: _history(ctx, sym))
    ctx.publish(DATASET, out, source="nse filings, yfinance", as_of=str(day))
    return f"published facts of {len(out)} stocks"


def _history(ctx, symbol: str) -> list[dict]:
    """Two years of daily rows from our own stock route, oldest first."""
    since = date(ctx.range.end.year - 2, ctx.range.end.month, min(ctx.range.end.day, 28)).isoformat()
    return ctx.client._ok(f"/api/stocks/{symbol}/history?from={since}", None, "GET").get("rows", [])


def _live(universe: list[dict], day: date):
    import yfinance as yf

    from stockpilot.sources import facts_sources as fs
    from stockpilot.sources.http import fetch
    from stockpilot.sources.nse_api import Session

    cache: dict[str, dict] = {}
    prices: dict[str, float] = {}
    by = {u["symbol"]: u for u in universe}

    def yf_info(symbol):
        cache[symbol] = yf.Ticker(symbol + ".NS").info
        return cache[symbol]
    base = fs.live_gather(Session(), fetch, yf_info, day)

    def gather(symbol):
        recs = base(symbol)
        info = cache.pop(symbol, {})
        by[symbol]["sector"] = info.get("sector") or ""
        if info.get("currentPrice"):
            prices[symbol] = float(info["currentPrice"])
        return recs
    return gather, prices


