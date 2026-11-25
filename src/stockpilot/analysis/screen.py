"""The screen: rank every liquid stock on quality, value, momentum and risk, each as a percentile
within its industry, and say why each excluded stock was dropped. Watchlist stocks always pass,
carrying their exclusion reasons as flags. Market health (breadth, Nifty trend) rides along."""
import json
import math
from datetime import date, timedelta

import duckdb

from stockpilot.analysis import analytics
from stockpilot.verify import flags

FACTORS = {  # metric -> True when higher is better
    "quality": {"roe": True, "roce": True, "debt_to_equity": False, "profit_cagr_3y": True},
    "value": {"pe": False, "pb": False},
    "momentum": {"ret_12m": True, "ret_6m": True, "dist_200dma": True},
    "risk": {"vol_1y": False, "max_dd_1y": True},
}
WEIGHTS = {"quality": 0.30, "value": 0.25, "momentum": 0.30, "risk": 0.15}
MIN_DAYS = 200
MIN_PEERS = 3


def _percentiles(values: dict[str, float], higher_is_better: bool) -> dict[str, float]:
    """Percentile in [0, 1] for each symbol; ties share a rank; a lone value gets 0.5."""
    items = sorted(values.items(), key=lambda kv: kv[1], reverse=higher_is_better)
    n = len(items)
    if n == 1:
        return {items[0][0]: 0.5}
    out, i = {}, 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][1] == items[i][1]:
            j += 1
        rank = 1 - ((i + j) / 2) / (n - 1)
        for k in range(i, j + 1):
            out[items[k][0]] = rank
        i = j + 1
    return out


FUNDAMENTALS_SLACK_DAYS = 7    # fundamentals change quarterly, so a snapshot a few days newer than the day is as good


def _latest_fundamentals(db, as_of):
    """The newest snapshot per metric dated up to a week after `as_of`. (The backtest does not read
    fundamentals; if it ever does, it must pass its own strict day.)"""
    rows = db.execute("""
        select symbol, metric, arg_max(value, as_of) from fundamentals where as_of <= ?
        group by symbol, metric""", [as_of + timedelta(days=FUNDAMENTALS_SLACK_DAYS)]).fetchall()
    out: dict[str, dict] = {}
    for symbol, metric, value in rows:
        out.setdefault(symbol, {})[metric] = value
    return out


KEEP_DAYS = 7          # stored screens older than this are dropped; they are only ever read for the latest day


def _plain(x):
    """JSON cannot hold NaN or infinity; a missing number is None."""
    if isinstance(x, float) and not math.isfinite(x):
        return None
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, list):
        return [_plain(v) for v in x]
    return x


def run(db: duckdb.DuckDBPyConnection, as_of: date, liquidity_floor_cr: float = 1.0,
        weights: dict | None = None, fresh: bool = False) -> dict:
    """The screen for `as_of`, computed once per trading day and kept in `screens`: the decide step, the site and the
    weekly opportunities all read the same one. `fresh` recomputes and replaces it (after new prices or fundamentals).
    Other weights are an experiment and never touch the stored one."""
    if weights is not None:
        return _compute(db, as_of, liquidity_floor_cr, weights)
    if not fresh:
        row = db.execute("select payload from screens where as_of = ?", [as_of]).fetchone()
        stored = json.loads(row[0]) if row else None
        if stored and stored.get("floor") == liquidity_floor_cr:
            return {**stored["result"], "as_of": as_of}
    result = _compute(db, as_of, liquidity_floor_cr, WEIGHTS)
    payload = json.dumps({"floor": liquidity_floor_cr, "result": _plain({**result, "as_of": str(as_of)})}, default=str)
    db.execute("insert or replace into screens values (?, ?)", [as_of, payload])
    db.execute("delete from screens where as_of < ?", [as_of - timedelta(days=KEEP_DAYS)])
    return result


def _compute(db: duckdb.DuckDBPyConnection, as_of: date, liquidity_floor_cr: float, weights: dict) -> dict:
    prices = {s: f for s, f in analytics.price_factors(db, as_of).items() if f["days"] >= MIN_DAYS}
    funda = _latest_fundamentals(db, as_of)
    industry = dict(db.execute("select symbol, industry from stocks").fetchall())
    flagged = dict(db.execute("select symbol, label from surveillance where as_of = "
                              "(select max(as_of) from surveillance where as_of <= ?)", [as_of]).fetchall())
    watch = {s for (s,) in db.execute("select symbol from watchlist where removed_at is null").fetchall()}
    unreliable = flags.flagged_symbols(db)      # lane V: an unexplained jump in the price series; never screened, even on the watchlist

    reasons: dict[str, list[str]] = {}
    for symbol, f in prices.items():
        r = []
        if symbol in unreliable:
            r.append(flags.flag_note(db, symbol))
        if symbol in flagged:
            r.append(f"surveillance: {flagged[symbol]}")
        if (f["adv_3m_cr"] or 0) < liquidity_floor_cr:
            r.append(f"illiquid (₹{f['adv_3m_cr'] or 0:.2f} cr a day)")
        reasons[symbol] = r
    pool = [s for s in prices if (not reasons[s] or s in watch) and s not in unreliable]

    metrics = {s: {**prices[s], **funda.get(s, {})} for s in pool}
    groups: dict[str, list[str]] = {}
    for s in pool:
        groups.setdefault(industry.get(s) or "Unknown", []).append(s)
    scores = {s: {} for s in pool}
    for group in groups.values():
        peers = group if len(group) >= MIN_PEERS else pool
        for factor, parts in FACTORS.items():
            ranks: dict[str, list[float]] = {s: [] for s in group}
            for metric, up in parts.items():
                vals = {s: metrics[s][metric] for s in peers if metrics[s].get(metric) is not None}
                if metric == "pe":
                    vals = {s: v for s, v in vals.items() if v > 0}
                pct = _percentiles(vals, up) if vals else {}
                for s in group:
                    ranks[s].append(pct.get(s, 0.0 if metric == "pe" and s in metrics and
                                            (metrics[s].get("pe") or 1) <= 0 else 0.5))
            for s in group:
                scores[s][factor] = sum(ranks[s]) / len(ranks[s])

    candidates = []
    for s in pool:
        composite = sum(weights[k] * v for k, v in scores[s].items())
        candidates.append({"symbol": s, "exchange": prices[s]["exchange"], "industry": industry.get(s),
                           "composite": composite, "scores": scores[s], "flags": reasons[s],
                           "watchlist": s in watch, "metrics": metrics[s]})
    candidates.sort(key=lambda c: (-c["composite"], c["symbol"]))      # lane V: ties break by symbol, never by the order the database returned rows

    above = [f["dist_200dma"] > 0 for f in prices.values() if f["dist_200dma"] is not None]
    nifty = db.execute("select close from index_levels where name = 'Nifty 50' and date <= ? "
                       "order by date desc limit 200", [as_of]).fetchall()
    health = {"breadth_above_200dma": round(sum(above) / len(above), 4) if above else None,
              "nifty_above_200dma": (nifty[0][0] > sum(c for (c,) in nifty) / len(nifty)) if len(nifty) >= 200 else None}
    excluded = {s: "; ".join(r) for s, r in reasons.items() if r and (s not in watch or s in unreliable)}
    return {"as_of": as_of, "candidates": candidates, "excluded": excluded, "health": health}
