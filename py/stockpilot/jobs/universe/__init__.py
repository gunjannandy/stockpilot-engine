"""The universe Job: every NSE, NSE SME, BSE and BSE SME stock, published as the `universe` dataset.

Public lists only. A stock that dropped off the lists stays, marked delisted (a name change keeps both names), so an old
holding still opens. A list that comes back far too small fails the Job instead of replacing a good universe."""
from collections.abc import Callable
from datetime import date, datetime, timedelta, timezone

from stockpilot.runtime import JobContext
from stockpilot.sources import search_index as si
from stockpilot.sources.marketdata import BSE_URL
from stockpilot.sources.universe import EQUITY_L, SME_L

KIND = DATASET = "universe"
IST = timezone(timedelta(hours=5, minutes=30))


def to_rows(entries: list[dict], previous: list[dict]) -> list[dict]:
    """Today's entries as `universe` rows, plus every earlier stock not listed today, marked delisted."""
    rows = {}
    for e in entries:
        rid = f"{e['exchange']}:{e['symbol']}"
        rows[rid] = {"id": rid, "symbol": e["symbol"], "exchange": e["exchange"], "segment": e["segment"], "name": e["name"],
                     "isin": e["isin"] or "", "aliases": "|".join(e["aliases"]), "status": "listed"}
    for p in previous:
        if p["id"] not in rows:
            rows[p["id"]] = {**p, "status": "delisted"}
    return [rows[k] for k in sorted(rows)]


def build(fetch: Callable[[str], bytes | None], today: date, previous: list[dict], days: int = 7, min_main: int = si.MIN_MAIN) -> list[dict]:
    bse_days = [fetch(BSE_URL.format(day=today - timedelta(days=i))) for i in range(days)]
    idx = si.build_index({"nse_main": fetch(EQUITY_L) or b"", "nse_sme": fetch(SME_L), "bse_days": bse_days,
                          "built_at": datetime.now(IST).isoformat(timespec="seconds"), "min_main": min_main})
    return to_rows(idx["entries"], previous)


def run(ctx: JobContext, fetch: Callable[[str], bytes | None] | None = None) -> str:
    if fetch is None:
        from stockpilot.sources.http import fetch
    try:
        previous = ctx.client._ok("/api/stocks/universe", None, "GET").get("rows", [])
    except RuntimeError:
        previous = []
    rows = build(fetch, ctx.range.end, previous)
    gone = sum(r["status"] == "delisted" for r in rows)
    ctx.progress.line(f"{len(rows)} stocks, {gone} no longer listed")
    ctx.publish(DATASET, rows, source="exchange lists", as_of=str(ctx.range.end))
    return f"published {len(rows)} stocks"
