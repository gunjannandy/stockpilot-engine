"""A synthetic market for the mechanical-forecast tests: neutral symbols, no real data. Each stock has a steady drift
(so momentum carries real information), shared market shocks, and its own noise."""
import numpy as np

from stockpilot.mechanical.panel import Panel


def make_panel(n=60, days=1100, seed=7, drift_scale=0.0010, noise=0.014) -> Panel:
    rng = np.random.default_rng(seed)
    drift = rng.normal(0, drift_scale, n)
    market = rng.normal(0.0003, 0.008, days)
    # the market trends in long swings so the 200-day regime flag changes
    market += 0.0008 * np.sin(np.arange(days) / 90.0)
    ret = market[:, None] + drift[None, :] + rng.normal(0, noise, (days, n))
    ret[0] = 0
    close = 100 * np.cumprod(1 + ret, axis=0)
    value = np.exp(rng.normal(16, 1.0, n))[None, :] * np.exp(rng.normal(0, 0.1, (days, n)))
    dates = np.array([np.datetime64("2020-01-01") + np.timedelta64(i, "D") for i in range(days)])
    keys = [("NSE" if i % 3 else "BSE", f"S{i:03d}") for i in range(n)]
    return Panel(dates=dates, keys=keys, close=close, value=value, bench=np.cumprod(1 + market) * 1000)
