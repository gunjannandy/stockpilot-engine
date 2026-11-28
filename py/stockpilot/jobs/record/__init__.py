"""The record Job, every night: score each call whose window has ended (did it beat the Nifty?) and work out whether we
are adding value: our Buy calls against holding the Nifty and against an equal-weight watchlist over the same windows.

Public data only (calls, closes, the Nifty). Pure functions over plain rows, so the same calls and prices always give the
same scores (fixtures prove it). Scores go to the Worker's insert-only door; the track record is read from them there."""
from datetime import date, timedelta

KIND = "record"
HURDLE = 0.01                  # beat the Nifty by this much (cost and tax allowance); same as the mechanical model's
WINDOW_DAYS = {63: 91, 126: 182}
PRICE_SLACK_DAYS = 7           # a price this far from the window edge is "no data", not a result
MIN_FOR_VERDICT = 30           # scored Buy calls before "adding value" is yes or no


def _day(x) -> date:
    return x if isinstance(x, date) else date.fromisoformat(str(x))


def on_or_before(rows: list, day: date):
    """Close on the last day at or before `day`, if within the slack."""
    best = None
    for d, v in rows:
        d = _day(d)
        if d <= day and (best is None or d > best[0]):
            best = (d, v)
    return best[1] if best and (day - best[0]).days <= PRICE_SLACK_DAYS else None


def window_return(rows: list, start: date, end: date) -> float | None:
    a, b = on_or_before(rows, start), on_or_before(rows, end)
    return None if not a or not b else b / a - 1


def score_calls(calls: list[dict], closes: dict[str, list], nifty: list, watchlist: list[str], today: date) -> list[dict]:
    """calls: [{id, symbol, made_on, horizon_days}]. A call is scored once its window has ended and the stock and the Nifty
    have prices at both ends; it beat the Nifty when its excess return is over the hurdle. Each score keeps the three
    returns "adding value" averages: the stock, the Nifty, and the watchlist's equal-weight average over the same window."""
    out = []
    for c in sorted(calls, key=lambda c: c["id"]):
        days = WINDOW_DAYS.get(c["horizon_days"])
        if not days:
            continue
        start = _day(c["made_on"])
        end = start + timedelta(days=days)
        if end > today:
            continue
        stock, bench = window_return(closes.get(c["symbol"]) or [], start, end), window_return(nifty, start, end)
        if stock is None or bench is None:
            continue
        peers = [r for sym in watchlist if (r := window_return(closes.get(sym) or [], start, end)) is not None]
        out.append({"call_id": c["id"], "beat": stock - bench > HURDLE, "scored_on": today.isoformat(),
                    "stock_ret": stock, "nifty_ret": bench, "equal_ret": _mean(peers)})
    return out


def _mean(xs):
    return sum(xs) / len(xs) if xs else None


def adding_value(scored_buys: list[dict]) -> dict:
    """scored_buys: the scores of Buy calls. Percent values are percent; `adding` is None under 30 scored Buy calls."""
    rows = [r for r in scored_buys if r.get("stock_ret") is not None]
    o, b = _mean([r["stock_ret"] for r in rows]), _mean([r["nifty_ret"] for r in rows])
    e = _mean([r["equal_ret"] for r in rows if r.get("equal_ret") is not None])

    def pct(x):
        return None if x is None else round(x * 100, 2)
    edge_b = None if o is None or b is None else o - b
    edge_e = None if o is None or e is None else o - e
    return {"n": len(rows), "ours_pct": pct(o), "nifty_pct": pct(b), "equal_weight_pct": pct(e),
            "edge_vs_nifty_pct": pct(edge_b), "edge_vs_equal_weight_pct": pct(edge_e),
            "adding": None if len(rows) < MIN_FOR_VERDICT or edge_b is None else edge_b > 0 and (edge_e is None or edge_e > 0)}


def run(ctx, inputs: dict | None = None, nifty: list | None = None) -> str:
    today = ctx.range.end
    inputs = inputs or ctx.client._ok("/api/record/inputs", None, "GET")
    nifty = nifty if nifty is not None else _live_nifty()
    closes = {s: [(_day(d), v) for d, v in rows] for s, rows in inputs["closes"].items()}
    scores = score_calls(inputs["calls"], closes, nifty, inputs.get("watchlist", []), today)
    written = 0
    for i in range(0, len(scores), 2000):
        written += ctx.client._ok("/api/record/scores", {"scores": scores[i:i + 2000]})["written"]
    ctx.publish("record_runs", [{"id": str(today), "day": str(today), "scored": written}], source="calls and price history",
                as_of=str(today))
    return f"{written} calls scored"


def _live_nifty() -> list:
    import yfinance as yf
    h = yf.Ticker("^NSEI").history(period="max", interval="1d")
    return [(d.date(), float(v)) for d, v in h["Close"].items()]
