"""The 12 number-only signals (docs/research/forecast-v2.md, section A), for every stock on one day.

Every signal looks only at rows up to and including day `t`. Ranks run across the stocks that have the history;
a stock without enough history gets NaN, never a guess. Signals that need data this module does not hold (quality,
sector-relative value, earnings growth, delivery %) come in through `extras` as {"NSE:SYMBOL": {name: number}}; with no
point-in-time history they are shown but never trained on. Delivery % and the 1-month reversal are information only."""
import warnings

import numpy as np

NAMES = ["momentum", "near_52w_high", "low_volatility", "quality", "sector_value", "market_regime", "size",
         "liquidity", "earnings_growth", "trend", "delivery_info", "reversal_1m_info"]
SKIP = 21          # the last month is skipped in the 6-1 and 12-1 momentum


def rank01(x: np.ndarray) -> np.ndarray:
    """Percentile rank 0..1 across the finite values; NaN stays NaN."""
    out = np.full(x.shape, np.nan)
    ok = np.isfinite(x)
    n = ok.sum()
    if n == 0:
        return out
    order = np.argsort(np.argsort(x[ok], kind="stable"), kind="stable")
    out[ok] = order / (n - 1) if n > 1 else 0.5
    return out


def _ret(close, t, a, b):
    """Return from `a` days ago to `b` days ago (a > b)."""
    with np.errstate(invalid="ignore", divide="ignore"):
        return close[t - b] / close[t - a] - 1


def raw(panel, t: int) -> dict:
    """The unranked numbers behind the signals; the model uses them as features."""
    c = panel.close
    keys = ("mom6", "mom12", "near", "vol", "dma50", "dma200", "ret21", "liq", "over200")
    if t < 252:
        return {k: np.full(panel.n_stocks, np.nan) for k in keys}
    window = c[t - 251:t + 1]
    with np.errstate(invalid="ignore", divide="ignore"), warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)     # all-NaN columns are stocks with no history: they stay NaN
        recent = c[t - 62:t + 1]
        daily = recent[1:] / recent[:-1] - 1
        have = np.isfinite(window).sum(axis=0) >= 240
        vol = np.where(np.isfinite(daily).sum(axis=0) >= 55, np.nanstd(daily, axis=0, ddof=1), np.nan)
        dma200 = np.nanmean(c[t - 199:t + 1], axis=0)
        dma50 = np.nanmean(c[t - 49:t + 1], axis=0)
        near = c[t] / np.nanmax(window, axis=0)
        liq = np.nanmedian(panel.value[t - 62:t + 1], axis=0)
        out = {"mom6": _ret(c, t, 126, SKIP), "mom12": _ret(c, t, 252, SKIP), "near": near, "vol": vol,
               "dma50": dma50, "dma200": dma200, "ret21": _ret(c, t, 21, 0), "liq": liq, "over200": c[t] / dma200}
    ok = have & np.isfinite(c[t])
    return {k: np.where(ok, v, np.nan) for k, v in out.items()}


def regime(panel, t: int) -> float:
    """1 when the benchmark sits above its own 200-day average, else 0; NaN before 200 days."""
    if t < 199:
        return float("nan")
    return float(panel.bench[t] > panel.bench[t - 199:t + 1].mean())


def compute(panel, t: int, extras: dict | None = None) -> dict:
    r = raw(panel, t)
    n = panel.n_stocks
    s = {name: np.full(n, np.nan) for name in NAMES}
    s["momentum"] = rank01(r["mom6"])
    s["near_52w_high"] = np.clip(r["near"], 0, 1)
    s["low_volatility"] = 1 - rank01(r["vol"])
    trend = ((r["over200"] > 1).astype(float) + (r["dma50"] > r["dma200"]).astype(float)) / 2
    s["trend"] = np.where(np.isfinite(r["dma200"]) & np.isfinite(r["over200"]), trend, np.nan)
    s["market_regime"] = np.where(np.isfinite(r["mom6"]), regime(panel, t), np.nan)
    s["liquidity"] = rank01(r["liq"])
    s["size"] = s["liquidity"].copy()          # no market cap in the price files: size follows traded value
    s["reversal_1m_info"] = r["ret21"]
    for i in range(n):
        for name, v in ((extras or {}).get(panel.key_text(i)) or {}).items():
            if name in s and v is not None:
                s[name][i] = v
    return s
