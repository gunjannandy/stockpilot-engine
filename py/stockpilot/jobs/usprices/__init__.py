"""The usprices Job: daily closes of the US shares we hold (RSUs), and USD/INR up to today.

The Worker says which dollar symbols are still held and from when (`GET /api/money/us-symbols`); the Job reads each
symbol's closes from Yahoo and posts them to `POST /api/money/us-prices` (an upsert, so a rerun is harmless), then asks the
Worker to fill USD/INR (`POST /api/money/fx-refresh`, the ECB feed through the Worker's own rate code). A series with a
move over 40% in a day is held back; the run fails only when every symbol is held back or none could be read.
Public market data only."""
import itertools
import json
from collections.abc import Callable
from datetime import UTC, date, datetime

from stockpilot.runtime import JobContext

KIND = DATASET = "usprices"
MOVE_LIMIT = 0.4


def chart_url(symbol: str, start: date, end: date) -> str:
    p1 = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
    p2 = int(datetime(end.year, end.month, end.day, 23, 59, tzinfo=UTC).timestamp())
    return (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            f"?period1={p1}&period2={p2}&interval=1d")


def closes(chart: object) -> list[dict]:
    result = ((chart or {}).get("chart") or {}).get("result") or []  # type: ignore[union-attr]
    if not result or not result[0].get("timestamp"):
        return []
    quote = result[0]["indicators"]["quote"][0]["close"]
    return [{"date": datetime.fromtimestamp(ts, UTC).date().isoformat(), "close": round(float(c), 4)}
            for ts, c in zip(result[0]["timestamp"], quote, strict=False) if c]


def unexplained_move(rows: list[dict], limit: float = MOVE_LIMIT) -> dict | None:
    """Splits show as a jump in raw closes, so a jump is held back rather than posted."""
    for a, b in itertools.pairwise(rows):
        if abs(b["close"] / a["close"] - 1) > limit:
            return {"date": b["date"], "from": a["close"], "to": b["close"]}
    return None


def run(ctx: JobContext, fetch_json: Callable[[str], object] | None = None) -> str:
    if fetch_json is None:
        from stockpilot.sources.http import fetch as raw

        def fetch_json(url):
            blob = raw(url)
            return json.loads(blob) if blob else None
    today = ctx.range.end
    want = ctx.client._ok("/api/money/us-symbols", None, "GET")
    symbols = want.get("symbols", [])
    if not symbols:
        ctx.progress.line("no dollar shares held")
        return "no dollar shares held"
    ctx.client._ok("/api/money/fx-refresh", {"since": want["fx_since"]})
    start = date.fromisoformat(want["since"])
    posted, held, empty, total = 0, {}, 0, 0
    for symbol in symbols:
        rows = closes(fetch_json(chart_url(symbol, start, today)))
        if not rows:
            empty += 1
            ctx.progress.line(f"{symbol}: no prices", "fail")
            continue
        bad = unexplained_move(rows)
        if bad:
            held[symbol] = bad
            ctx.progress.line(f"{symbol} held back: moved {bad['from']} to {bad['to']} on {bad['date']}", "fail")
            continue
        ctx.client._ok("/api/money/us-prices", {"symbol": symbol, "rows": rows})
        posted += 1
        total += len(rows)
    if posted == 0:
        raise RuntimeError(f"no prices posted: {len(held)} held back, {empty} without prices")
    ctx.publish(DATASET, [{"id": str(today), "day": str(today), "symbols": posted, "rows": total, "held_back": len(held)}],
                source="yahoo chart", as_of=str(today))
    return f"posted {posted} symbols, held back {len(held)}"
