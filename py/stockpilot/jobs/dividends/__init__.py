"""The dividends Job: cash dividends per share by ex-date for the Indian stocks we hold.

The Worker says which stocks are held and since when (`GET /api/money/held-symbols`); the Job reads each stock's
dividend events from Yahoo's chart feed and posts them to `POST /api/money/dividends` (an upsert, so a rerun is harmless).
The Calendar's expected cash is last year's dividends, one year on. A stock whose feed cannot be read is skipped; the run
fails only when no stock could be read. Public market data only."""
import json
from collections.abc import Callable
from datetime import UTC, date, datetime

from stockpilot.runtime import JobContext

KIND = DATASET = "dividends"


def chart_url(symbol: str, start: date, end: date) -> str:
    p1 = int(datetime(start.year, start.month, start.day, tzinfo=UTC).timestamp())
    p2 = int(datetime(end.year, end.month, end.day, 23, 59, tzinfo=UTC).timestamp())
    return (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.NS"
            f"?period1={p1}&period2={p2}&interval=1d&events=div")


def dividends(chart: object) -> list[dict]:
    result = ((chart or {}).get("chart") or {}).get("result") or []  # type: ignore[union-attr]
    if not result:
        return []
    events = ((result[0].get("events") or {}).get("dividends")) or {}
    return sorted(({"ex_date": datetime.fromtimestamp(e["date"], UTC).date().isoformat(), "per_share": round(float(e["amount"]), 4)}
                   for e in events.values() if e.get("amount")), key=lambda r: r["ex_date"])


def run(ctx: JobContext, fetch_json: Callable[[str], object] | None = None) -> str:
    if fetch_json is None:
        from stockpilot.sources.http import fetch as raw

        def fetch_json(url):
            blob = raw(url)
            return json.loads(blob) if blob else None
    want = ctx.client._ok("/api/money/held-symbols", None, "GET")
    symbols = want.get("symbols", [])
    if not symbols:
        ctx.progress.line("no Indian stocks held")
        return "no stocks held"
    start = max(date.fromisoformat(want["since"]), date(ctx.range.end.year - 2, 1, 1))
    read, total = 0, 0
    for symbol in symbols:
        try:
            rows = dividends(fetch_json(chart_url(symbol, start, ctx.range.end)))
        except (OSError, ValueError, KeyError) as e:  # one stock's feed failing must not stop the rest
            ctx.progress.line(f"{symbol}: {e}", "fail")
            continue
        read += 1
        if rows:
            ctx.client._ok("/api/money/dividends", {"symbol": symbol, "rows": rows})
            total += len(rows)
    if read == 0:
        raise RuntimeError(f"no dividend feed could be read for {len(symbols)} stocks")
    ctx.publish(DATASET, [{"id": str(ctx.range.end), "day": str(ctx.range.end), "symbols": read, "rows": total}],
                source="yahoo chart", as_of=str(ctx.range.end))
    return f"read {read} stocks, {total} dividends"
