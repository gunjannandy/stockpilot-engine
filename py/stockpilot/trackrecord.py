"""T20: score every call at 1, 3 and 6 months. Pure functions over plain rows, so the same calls and prices always give the
same scores (a fixture proves it). The forecaster never imports this module: a call is judged here, after the fact.

A call's outcome is "beat the Nifty 50 by more than the call's hurdle" over the window (91 days for 3 months, 182 for 6, 30
for 1). The chance a call states is the chance of that outcome, so Brier is (chance - outcome)^2; the base rate alone (the
mechanical start) is scored on the same call. A buy or add is a hit when it beat the Nifty, a sell or trim when it did not;
hold, wait and the rest give a Brier but no hit. One month has no chance in the v2 form (a range only), so it is judged on
whether the price landed inside the stated range. News buys (route "news") are summarised apart, linked to their news."""
from datetime import date, timedelta

WINDOWS = (("1m", 30), ("3m", 91), ("6m", 182))
PRICE_SLACK_DAYS = 7           # a price this far from the window edge is "no data", not a result
BUY_SIDE = {"buy", "add"}
SELL_SIDE = {"sell", "trim"}
TOO_EARLY = 30                 # scored calls per route and horizon before the numbers are called a result
LEAN_UNTIL = 100               # between TOO_EARLY and this, the line says "a lean, not a result"
ROUTES = ("code", "news")


def _on_or_before(rows, day: date):
    best = None
    for d, v in rows:
        if d <= day and (best is None or d > best[0]):
            best = (d, v)
    return best[1] if best and (day - best[0]).days <= PRICE_SLACK_DAYS else None


def _latest_per_day(calls: list[dict]) -> list[dict]:
    """The later call stands when a stock was called twice on one day, so a rerun counts once."""
    kept: dict[tuple, dict] = {}
    for c in calls:
        kept[(c["symbol"], c["exchange"], c["made_on"])] = c
    return list(kept.values())


def score_calls(calls: list[dict], prices: dict[str, list], nifty: list, today: date) -> list[dict]:
    """One row per call and finished window: {symbol, exchange, made_on, route, call, horizon, excess, hit, brier,
    base_brier, in_range, chance, news_ids, model, adjustments}. A window not yet ended, or without prices at both ends
    for the stock and the Nifty, gives no row."""
    out = []
    for c in _latest_per_day(calls):
        rows = prices.get(c["symbol"]) or []
        for horizon, days in WINDOWS:
            end = c["made_on"] + timedelta(days=days)
            if end > today:
                continue
            s0, s1 = _on_or_before(rows, c["made_on"]), _on_or_before(rows, end)
            n0, n1 = _on_or_before(nifty, c["made_on"]), _on_or_before(nifty, end)
            if not (s0 and s1 and n0 and n1):
                continue
            excess = (s1 / s0 - 1) - (n1 / n0 - 1)
            beat = 1 if excess > (c.get("hurdle") or 0.0) else 0
            chance, base = (c.get(f"chance_{horizon}"), c.get(f"base_{horizon}")) if horizon != "1m" else (None, None)
            hit = None
            if c["call"] in BUY_SIDE:
                hit = beat
            elif c["call"] in SELL_SIDE:
                hit = 1 - beat
            rng = c.get("range_1m") if horizon == "1m" else None
            out.append({
                "symbol": c["symbol"], "exchange": c["exchange"], "made_on": c["made_on"], "route": c.get("route", "code"),
                "call": c["call"], "horizon": horizon, "excess": excess, "beat": beat, "hit": hit,
                "chance": None if chance is None else chance / 100,
                "brier": None if chance is None else (chance / 100 - beat) ** 2,
                "base_brier": None if base is None else (base / 100 - beat) ** 2,
                "in_range": None if not rng else rng["low"] <= s1 <= rng["high"],
                "news_ids": list(c.get("news_ids") or []), "model": c.get("model"),
                "adjustments": list(c.get("adjustments") or [])})
    return out


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _calibration(rows: list[dict]) -> list[dict]:
    """Bins of 0.1: what was said against what happened, with n."""
    bins: dict[int, list] = {}
    for r in rows:
        if r["chance"] is not None:
            bins.setdefault(min(9, int(r["chance"] * 10)), []).append(r)
    return [{"said": round(sum(r["chance"] for r in v) / len(v), 3), "happened": round(sum(r["beat"] for r in v) / len(v), 3),
             "n": len(v)} for _, v in sorted(bins.items())]


def _verdict(n: int) -> str:
    return "too early" if n < TOO_EARLY else "a lean" if n < LEAN_UNTIL else "a result"


def _line(route: str, horizon: str, n: int, hit_rate, brier, base_brier) -> str:
    words = {"1m": "1 month", "3m": "3 months", "6m": "6 months"}[horizon]
    who = "News buys" if route == "news" else "Calls"
    if n < TOO_EARLY:
        return f"{who} over {words}: {n} scored so far, too early to say how good they are (we wait for {TOO_EARLY})."
    if hit_rate is None or brier is None or base_brier is None:
        return f"{who} over {words}: {n} scored."
    better = "better than" if brier < base_brier else "no better than"
    return (f"{who} over {words}: {n} scored, {round(100 * hit_rate)}% right, Brier {brier:.3f}, {better} the base rate "
            f"alone ({base_brier:.3f}); {_verdict(n)}.")


def summary(rows: list[dict]) -> dict:
    """{route: {horizon: {n, hit_rate, brier, base_brier, calibration, range_coverage, verdict, line}}}. Routes are code and
    news, never mixed."""
    out = {}
    for route in ROUTES:
        out[route] = {}
        for horizon, _ in WINDOWS:
            rs = [r for r in rows if r["route"] == route and r["horizon"] == horizon]
            hit_rate, brier, base_brier = _mean([r["hit"] for r in rs]), _mean([r["brier"] for r in rs]), _mean([r["base_brier"] for r in rs])
            ranged = [r["in_range"] for r in rs if r["in_range"] is not None]
            out[route][horizon] = {
                "n": len(rs), "hit_rate": hit_rate, "brier": brier, "base_brier": base_brier,
                "calibration": _calibration(rs) if horizon != "1m" else [],
                "range_coverage": (sum(ranged) / len(ranged)) if ranged else None,
                "verdict": _verdict(len(rs)), "line": _line(route, horizon, len(rs), hit_rate, brier, base_brier)}
    return out


def news_buys(rows: list[dict], news: dict[str, dict]) -> list[dict]:
    """Each news buy with the news that made it and its result at each window scored so far. `news` maps an id to
    {title, link}; an id we no longer hold shows with no title."""
    grouped: dict[tuple, dict] = {}
    for r in sorted((r for r in rows if r["route"] == "news"), key=lambda r: (r["made_on"], r["symbol"], r["horizon"])):
        g = grouped.setdefault((r["symbol"], r["exchange"], r["made_on"]), {
            "symbol": r["symbol"], "exchange": r["exchange"], "made_on": r["made_on"].isoformat(),
            "news": [{"id": i, "title": (news.get(i) or {}).get("title"), "link": (news.get(i) or {}).get("link")} for i in r["news_ids"]],
            "results": {}})
        g["results"][r["horizon"]] = r["hit"]
    return list(grouped.values())
