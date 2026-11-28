"""The history Job. Subject `all`: append the newest trading days' prices for every stock. Subject a symbol: load that
one stock's whole history (the load Job the stock page starts for a symbol it holds nothing for).

Prices go to the Worker's `POST /api/stocks/history`, one stock a call; the Worker upserts, so a rerun is harmless.
A stock whose series has a move over 40% that nothing explains is held back with its reason; the run fails only when
more than 2% of stocks are held back. Public market data only."""
import itertools
import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from stockpilot.runtime import JobContext
from stockpilot.sources import history as h

KIND = "history"
MOVE_LIMIT = 0.4
HELD_BACK_LIMIT = 0.02
LOOKBACK_DAYS = 5
FIRST_LISTING = date(1994, 11, 3)


def unexplained_move(rows: list[dict], explained: set[str] | frozenset[str] = frozenset(), limit: float = MOVE_LIMIT) -> dict | None:
    """The first day whose close is more than `limit` from the day before, unless a corporate action explains that date."""
    rows = sorted(rows, key=lambda r: str(r["date"]))
    for a, b in itertools.pairwise(rows):
        if not a["close"] or str(b["date"]) in explained:
            continue
        if abs(b["close"] / a["close"] - 1) > limit:
            return {"date": str(b["date"]), "from": a["close"], "to": b["close"]}
    return None


def _post(ctx: JobContext, exchange: str, symbol: str, rows: list[dict]) -> None:
    body = [{"date": str(r["date"]), "open": r.get("open"), "high": r.get("high"), "low": r.get("low"), "close": r["close"],
             "prev_close": r.get("prev_close"), "volume": r.get("volume")} for r in rows]
    for i in range(0, len(body), 2000):
        ctx.client._ok("/api/stocks/history", {"symbol": symbol, "exchange": exchange, "rows": body[i:i + 2000]})


def daily_rows(fetch: Callable[[str], bytes | None], today: date, lookback: int = LOOKBACK_DAYS) -> dict[tuple[str, str], list[dict]]:
    """Newest days' rows for every stock, grouped by (exchange, symbol). A day with no file (holiday) adds nothing."""
    out: dict[tuple[str, str], list[dict]] = {}
    for exchange in h.EXCHANGES:
        for day in h.weekdays(today - timedelta(days=lookback - 1), today):
            for r in h.PARSERS[exchange](fetch(h.URLS[exchange](day)), day):
                sym = r.get("symbol") or r.get("code")
                if sym and r.get("close"):
                    out.setdefault((exchange, sym), []).append(r)
    return out


def hold_back(by_stock: dict[tuple[str, str], list[dict]]) -> tuple[dict, dict[str, dict]]:
    """Split the stocks into ones to post and ones held back (symbol -> reason). The exchange's own prev_close is corrected on
    an ex-date, so close / prev_close is the true step and a split alone never trips this."""
    good, held = {}, {}
    for key, rows in by_stock.items():
        bad = next(({"date": str(r["date"]), "from": r["prev_close"], "to": r["close"]} for r in rows
                    if r.get("prev_close") and abs(r["close"] / r["prev_close"] - 1) > MOVE_LIMIT), None)
        if bad:
            held[f"{key[0]}:{key[1]}"] = bad
        else:
            good[key] = rows
    return good, held


def yahoo_rows(symbol: str, exchange: str, fetch_json: Callable[[str], object], today: date) -> list[dict]:
    chart = fetch_json(h.yahoo_url(symbol, exchange, FIRST_LISTING, today))
    result = ((chart or {}).get("chart") or {}).get("result") or []  # type: ignore[union-attr]
    if not result or not result[0].get("timestamp"):
        return []
    q = result[0]["indicators"]["quote"][0]
    rows, prev = [], None
    for i, ts in enumerate(result[0]["timestamp"]):
        if q["close"][i] is None:
            continue
        rows.append({"date": datetime.fromtimestamp(ts, UTC).date(), "open": q["open"][i], "high": q["high"][i],
                     "low": q["low"][i], "close": q["close"][i], "prev_close": prev, "volume": q["volume"][i]})
        prev = q["close"][i]
    return rows


def load_one(ctx: JobContext, symbol: str, fetch_json: Callable[[str], object], today: date) -> str:
    for exchange in h.EXCHANGES:
        rows = yahoo_rows(symbol, exchange, fetch_json, today)
        if rows:
            bad = unexplained_move(rows)
            if bad:
                raise RuntimeError(f"{symbol} held back: price moved from {bad['from']} to {bad['to']} on {bad['date']} "
                                   "and no corporate action explains it")
            _post(ctx, exchange, symbol, rows)
            ctx.progress.line(f"{symbol}: {len(rows)} days on {exchange}", "ok")
            return f"loaded {len(rows)} days of {symbol}"
    raise RuntimeError(f"no price history found for {symbol}")


def run(ctx: JobContext, fetch: Callable[[str], bytes | None] | None = None,
        fetch_json: Callable[[str], object] | None = None) -> str:
    today = ctx.range.end
    if ctx.subject != "all":
        if fetch_json is None:
            from stockpilot.sources.http import fetch as raw

            def fetch_json(url):
                blob = raw(url)
                return json.loads(blob) if blob else None
        return load_one(ctx, ctx.subject.upper(), fetch_json, today)
    if fetch is None:
        from stockpilot.sources.http import fetch
    good, held = hold_back(daily_rows(fetch, today))
    for (exchange, symbol), rows in good.items():
        _post(ctx, exchange, symbol, rows)
    total = len(good) + len(held)
    for name, why in sorted(held.items()):
        ctx.progress.line(f"{name} held back: moved {why['from']} to {why['to']} on {why['date']}, no corporate action", "fail")
    if not total:
        ctx.progress.line("no prices published yet for these days")
        return "no new prices"
    if len(held) / total > HELD_BACK_LIMIT:
        raise RuntimeError(f"{len(held)} of {total} stocks held back for unexplained moves (limit {HELD_BACK_LIMIT:.0%})")
    return f"posted {len(good)} stocks, held back {len(held)}"
