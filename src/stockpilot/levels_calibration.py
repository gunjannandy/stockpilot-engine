"""Measure how far a target can sit. For every stock and start day in the price history: did the price reach
`entry + share x swing` (swing = daily move x sqrt(63)) within 63 trading days before it touched the stop? Per bucket
(volatility x size) the share that is reached about one time in two is stored in `config/levels_calibration.json`,
which `levels.py` reads. Rebuildable: `scripts/calibrate_levels.py`. Read-only on the database."""
import json
from functools import lru_cache
from pathlib import Path

PATH = Path(__file__).resolve().parents[2] / "config" / "levels_calibration.json"
HORIZON = 63
LOOKBACK = 130                 # days of history the support search needs (dossier.SWING_LOOKBACK)
SHARES = (0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 1.0)
TARGET_RATE = 0.5
FALLBACK = "all"
VOL_CUTS = (0.018, 0.03)       # daily move as a share of price: calm, middling, jumpy
SIZE_CUTS = (10.0, 100.0)      # average traded value in crore a day: small, middling, large (market cap is not stored)


def bucket(atr_pct, liquidity_cr) -> str:
    if atr_pct is None or liquidity_cr is None:
        return FALLBACK
    v = sum(atr_pct >= c for c in VOL_CUTS)
    s = sum(liquidity_cr >= c for c in SIZE_CUTS)
    return f"{('calm', 'mid', 'jumpy')[v]}/{('small', 'mid', 'large')[s]}"


def _atr(highs, lows, closes, i, n=14):
    tr = [max(highs[k] - lows[k], abs(highs[k] - closes[k - 1]), abs(lows[k] - closes[k - 1])) for k in range(i - n + 1, i + 1)]
    return sum(tr) / n


def measure_series(highs, lows, closes, shares=SHARES, step=5):
    """One outcome per start day: {'i', 'hit': {share: 0|1}, 'stopped': 0|1, 'shaken': 0|1}.
    A day that touches both stop and target counts the stop first (the careful reading)."""
    from stockpilot import dossier, levels
    out = []
    for i in range(LOOKBACK, len(closes) - HORIZON, step):
        atr = _atr(highs, lows, closes, i)
        if atr <= 0:
            continue
        entry = closes[i]
        support, _ = dossier.swing_levels(highs[:i + 1], lows[:i + 1], entry, atr)
        stop = levels.stop_for({"close": entry, "atr": atr, "support": support})[0]
        swing = atr * HORIZON ** 0.5
        goals = {s: entry + s * swing for s in shares}
        hit, stopped_at = {s: 0 for s in shares}, None
        for k in range(i + 1, i + HORIZON + 1):
            if lows[k] <= stop:
                stopped_at = k
                break
            for s, g in goals.items():
                if not hit[s] and highs[k] >= g:
                    hit[s] = 1
        out.append({"i": i, "hit": hit, "stopped": int(stopped_at is not None),
                    "shaken": int(stopped_at is not None and closes[i + HORIZON] > entry)})
    return out


def choose_share(curve: dict, rate: float = TARGET_RATE) -> float:
    """The share whose hit rate is `rate`, interpolated; the nearest end of the grid when none is."""
    pts = sorted((float(s), r) for s, r in curve.items())
    if pts[0][1] <= rate:
        return pts[0][0]
    for (s0, r0), (s1, r1) in zip(pts, pts[1:]):
        if r0 >= rate >= r1:
            return s0 if r0 == r1 else round(s0 + (s1 - s0) * (r0 - rate) / (r0 - r1), 3)
    return pts[-1][0]


def build(per_bucket: dict[str, list[dict]]) -> dict:
    """per_bucket: outcomes (from measure_series) grouped by bucket. Returns the stored calibration."""
    pooled = [o for v in per_bucket.values() for o in v]
    out = {"v": 1, "default_share": 0.5, "target_rate": TARGET_RATE, "buckets": {}}
    for name, rows in {**per_bucket, FALLBACK: pooled}.items():
        if len(rows) < 200:
            continue
        curve = {str(s): round(sum(o["hit"][s] for o in rows) / len(rows), 4) for s in rows[0]["hit"]}
        out["buckets"][name] = {"share": choose_share(curve), "curve": curve, "n": len(rows),
                                "stop_first": round(sum(o["stopped"] for o in rows) / len(rows), 4),
                                "shaken_out": round(sum(o["shaken"] for o in rows) / len(rows), 4)}
    return out


@lru_cache(maxsize=1)
def load() -> dict:
    try:
        return json.loads(PATH.read_text()).get("buckets") or {}
    except (OSError, ValueError):
        return {}


def _entry(p: dict):
    b = load()
    return b.get(bucket(p.get("atr_pct"), p.get("liquidity_cr"))) or b.get(FALLBACK)


def share_for(p: dict) -> float:
    e = _entry(p)
    return e["share"] if e else 0.5


def hit_rate_for(p: dict, share: float):
    """(rate, n) read off the bucket's curve at this share; None when nothing was measured."""
    e = _entry(p)
    if not e:
        return None
    pts = sorted((float(s), r) for s, r in e["curve"].items())
    share = min(max(share, pts[0][0]), pts[-1][0])
    for (s0, r0), (s1, r1) in zip(pts, pts[1:]):
        if s0 <= share <= s1:
            r = r0 if s1 == s0 else r0 + (r1 - r0) * (share - s0) / (s1 - s0)
            return round(r, 2), e["n"]
    return round(pts[-1][1], 2), e["n"]
