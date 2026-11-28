"""The market health Job, every trading evening: the Nifty's trend against its 200-day average, breadth (the share of the
largest stocks above their own 200-day average), and the value band (the middle P/E of stocks with a profit: cheap, fair or
dear). Public data only. A figure the sources do not give is left empty, never guessed; one row a day goes to `market`."""
import json
from datetime import date

from .templates import render

KIND = DATASET = "market"
DMA = 200
BREADTH_TOP = 500
BREADTH_MIN = 100
EDGES = (18.0, 24.0)       # median P/E: under the first is cheap, over the second dear (contract VALUE_BAND_EDGES)


def trend(closes: list[float]) -> tuple[float | None, float | None, str | None]:
    """(last close, percent above the 200-day average, up or down); all None under 200 days."""
    if len(closes) < DMA:
        return None, None, None
    avg = sum(closes[-DMA:]) / DMA
    pct = (closes[-1] / avg - 1) * 100
    return closes[-1], round(pct, 2), "up" if pct >= 0 else "down"


def breadth(series: dict[str, list[float]]) -> tuple[float | None, int]:
    """Share (percent) of stocks whose last close is above their 200-day average, among those with 200 days."""
    have = [c for c in series.values() if len(c) >= DMA]
    if len(have) < BREADTH_MIN:
        return None, len(have)
    return round(100 * sum(c[-1] > sum(c[-DMA:]) / DMA for c in have) / len(have), 1), len(have)


def value_band(pes: list[float]) -> tuple[float | None, str | None]:
    vals = sorted(p for p in pes if p and p > 0)
    if len(vals) < BREADTH_MIN:
        return None, None
    mid = vals[len(vals) // 2] if len(vals) % 2 else (vals[len(vals) // 2 - 1] + vals[len(vals) // 2]) / 2
    return round(mid, 1), "cheap" if mid < EDGES[0] else "dear" if mid > EDGES[1] else "fair"


def row(day: date, nifty: list[float], series: dict[str, list[float]], pes: list[float]) -> dict:
    close, pct, direction = trend(nifty)
    b, n = breadth(series)
    pe, band = value_band(pes)
    s = []
    if direction:
        s.append(render("trend_up" if direction == "up" else "trend_down", pct=f"{abs(pct):.1f}"))
    if b is not None:
        s.append(render("breadth", pct=f"{b:.0f}", n=str(n)))
    if band:
        s.append(render(f"value_{band}", pe=f"{pe:.0f}"))
    return {"id": day.isoformat(), "day": day.isoformat(), "nifty_close": None if close is None else round(close, 2),
            "nifty_trend_pct": pct, "nifty_trend": direction, "breadth_pct": b, "breadth_n": n, "median_pe": pe,
            "value_band": band, "sentences_json": json.dumps(s, ensure_ascii=False, separators=(",", ":"))}


def run(ctx, nifty: list[float] | None = None, series: dict | None = None, pes: list[float] | None = None) -> str:
    day = ctx.range.end
    if nifty is None or series is None or pes is None:
        nifty, series, pes = _live(ctx)
    out = row(day, nifty, series, pes)
    ctx.publish(DATASET, [out], source="nse index, price history, facts", as_of=str(day))
    return f"market health for {day}: trend {out['nifty_trend']}, breadth {out['breadth_pct']}, value {out['value_band']}"


def _live(ctx):
    import yfinance as yf
    facts = ctx.client._ok("/api/job-data/facts", None, "GET").get("rows", [])
    pes = [r["pe"] for r in facts if r.get("pe")]
    top = [r["symbol"] for r in sorted(facts, key=lambda r: -(r.get("market_cap_cr") or 0))[:BREADTH_TOP]]
    nifty = [float(v) for v in yf.Ticker("^NSEI").history(period="1y", interval="1d")["Close"].dropna()]
    series: dict[str, list[float]] = {}
    if top:
        data = yf.download([s + ".NS" for s in top], period="1y", interval="1d", progress=False, group_by="column")["Close"]
        for s in top:
            col = data.get(s + ".NS")
            if col is not None:
                series[s] = [float(v) for v in col.dropna()]
    return nifty, series, pes
