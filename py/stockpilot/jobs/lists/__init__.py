"""The lists Job: Worth following's lists with the reasons for each stock, rebuilt through market hours so "busy today"
stays current (each row carries its updated time). Public data only: "you hold" needs the holdings and is built in the
browser from `money`; nothing private reaches this Job.

Lists: top10 and just_missed (the screen's ranks 1 to 10 and 11 to 20), has_view (the calls that say Buy or Watch),
falling (the weakest tenth on momentum), busy_today (today's biggest movers among quotes we hold)."""
from datetime import datetime

from stockpilot.io.clock import ist_now, ist_text

from .templates import render

KIND = DATASET = "lists"
TOP_N = 10
MISSED_TO = 20
BUSY_MAX = 20
FALLING_MAX = 10
FALLING_AT = 0.10
VIEW_VERDICTS = ("Buy", "Watch")
TOP_FACTOR = 0.85       # a factor at or above this percentile is named as a reason


def _row(list_id: str, r: dict, position: int, reasons: list[dict], at: str) -> dict:
    return {"id": f"{list_id}:{r['symbol']}", "list": list_id, "symbol": r["symbol"], "exchange": r["exchange"],
            "position": position, "reasons_json": _dump(reasons), "updated_at": at}


def _dump(x) -> str:
    import json
    return json.dumps(x, ensure_ascii=False, separators=(",", ":"))


def _factor_reasons(r: dict) -> list[dict]:
    out = []
    for key, f in (("quality_top", "quality"), ("value_top", "value"), ("momentum_top", "momentum"), ("risk_top", "risk")):
        if r.get(f) is not None and r[f] >= TOP_FACTOR:
            out.append(render(key))
    return out


def build(screen: list[dict], calls: list[dict], movers: list[dict], at: str) -> list[dict]:
    """screen: the screen file's rows; calls: [{symbol, exchange, verdict, chance}]; movers: [{symbol, move_pct}]."""
    passed = sorted((r for r in screen if r.get("rank")), key=lambda r: r["rank"])
    rows = []
    for r in passed[:TOP_N]:
        rows.append(_row("top10", r, r["rank"], [render("rank", rank=str(r["rank"]), passed=str(len(passed)))] + _factor_reasons(r), at))
    for r in passed[TOP_N:MISSED_TO]:
        rows.append(_row("just_missed", r, r["rank"] - TOP_N, [render("missed", rank=str(r["rank"]))] + _factor_reasons(r), at))
    known = {(r["exchange"], r["symbol"]): r for r in screen}
    view = [c for c in calls if c["verdict"] in VIEW_VERDICTS and c.get("chance") is not None]
    view.sort(key=lambda c: (-c["chance"], c["symbol"]))
    for i, c in enumerate(view, 1):
        rows.append(_row("has_view", c, i, [render("has_view", verdict=c["verdict"], chance=str(round(c["chance"] * 100)))], at))
    falling = sorted((r for r in screen if r.get("momentum") is not None and r["momentum"] <= FALLING_AT and r.get("score") is not None),
                     key=lambda r: (r["momentum"], r["symbol"]))
    for i, r in enumerate(falling[:FALLING_MAX], 1):
        rows.append(_row("falling", r, i, [render("falling")], at))
    by_symbol = {r["symbol"]: r for r in screen}
    for i, m in enumerate(movers[:BUSY_MAX], 1):
        base = by_symbol.get(m["symbol"]) or known.get(("NSE", m["symbol"])) or {"symbol": m["symbol"], "exchange": "NSE"}
        key = "busy_up" if m["move_pct"] >= 0 else "busy_down"
        rows.append(_row("busy_today", base, i, [render(key, move=f"{abs(m['move_pct']):.1f}")], at))
    return rows


def run(ctx, screen: list[dict] | None = None, calls: list[dict] | None = None, movers: list[dict] | None = None,
        now: datetime | None = None) -> str:
    at = ist_text(now or ist_now())
    if screen is None:
        inputs = ctx.client._ok("/api/lists/inputs", None, "GET")
        calls, movers = inputs["calls"], inputs["movers"]
        if not inputs.get("screen"):
            raise RuntimeError("no screen file yet")
        screen = ctx.client._ok(inputs["screen"]["file"], None, "GET")["rows"]
    rows = build(screen, calls or [], movers or [], at)
    ctx.publish(DATASET, rows, source="the screen, the calls and near-live quotes", as_of=at)
    return f"{len(rows)} list rows"
