"""A price panel: one row per trading day, one column per stock, built from the all-time history files (T5).

Prices in the history are raw. The exchange's own `prev_close` is already corrected for splits, bonuses and dividends on
the ex-date, so the adjusted close is the running product of close / prev_close. No separate actions file is needed.
A stock is one column per (exchange, symbol); a company on both exchanges is two columns, as the contract has an
`exchange` field. The benchmark is the Nifty 50 when given, else the median daily move of the 300 most traded stocks
(stated in the report; the history files hold stocks only)."""
import warnings
from dataclasses import dataclass

import numpy as np

LIQUID_FOR_PROXY = 300


@dataclass
class Panel:
    dates: np.ndarray            # (T,) datetime64[D]
    keys: list                   # (exchange, symbol) per column
    close: np.ndarray            # (T, N) adjusted close, NaN where not trading
    value: np.ndarray            # (T, N) traded value, NaN where not trading
    bench: np.ndarray            # (T,) benchmark level

    @property
    def n_days(self) -> int:
        return len(self.dates)

    @property
    def n_stocks(self) -> int:
        return len(self.keys)

    def key_text(self, i: int) -> str:
        return f"{self.keys[i][0]}:{self.keys[i][1]}"


def market_proxy(close: np.ndarray, value: np.ndarray) -> np.ndarray:
    """Median daily move of the most traded stocks, as a level starting at 1000."""
    mean_value = np.nanmean(value, axis=0)
    order = np.argsort(-np.nan_to_num(mean_value, nan=-1))[:LIQUID_FOR_PROXY]
    c = close[:, order]
    with np.errstate(invalid="ignore", divide="ignore"):
        step = c[1:] / c[:-1] - 1
    step = np.where(np.isfinite(step), step, np.nan)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)       # the first day has no move: median is NaN, treated as 0
        med = np.nanmedian(np.vstack([np.full((1, step.shape[1]), np.nan), step]), axis=1)
    return 1000 * np.cumprod(1 + np.nan_to_num(med, nan=0.0))


def from_history(con, years: int = 9, bench_by_date: dict | None = None) -> Panel:
    """Load the last `years` of the `prices` view of an open history connection (see history.open_history)."""
    rows = con.execute(
        "select exchange, coalesce(symbol, code) as sym, date, close, prev_close, value from prices "
        "where close is not null and close > 0 and date >= (select max(date) from prices) - to_years(?) "
        "order by exchange, sym, date", [years]).fetchnumpy()
    d = rows["date"].astype("datetime64[D]")
    dates = np.unique(d)
    index = {x: i for i, x in enumerate(dates)}
    ex, sym = rows["exchange"], rows["sym"]
    close_raw = np.ma.getdata(rows["close"]).astype(float)
    prev = np.ma.filled(np.ma.asarray(rows["prev_close"], dtype=float), np.nan)
    val = np.ma.filled(np.ma.asarray(rows["value"], dtype=float), np.nan)
    cols: dict = {}
    for i in range(len(close_raw)):
        cols.setdefault((str(ex[i]), str(sym[i])), []).append(i)
    keys = sorted(cols)
    close = np.full((len(dates), len(keys)), np.nan)
    value = np.full_like(close, np.nan)
    for j, k in enumerate(keys):
        idx = np.array(cols[k])
        c, p = close_raw[idx], prev[idx]
        with np.errstate(invalid="ignore", divide="ignore"):
            step = np.where(np.isfinite(p) & (p > 0), c / p, np.nan)
            fallback = np.concatenate([[1.0], c[1:] / c[:-1]])   # no prev_close: the last close we hold
        step = np.where(np.isnan(step), fallback, step)
        step[0] = 1.0
        pos = [index[x] for x in d[idx]]
        close[pos, j] = c[0] * np.cumprod(step)
        value[pos, j] = val[idx]
    if bench_by_date:
        bench = _fill_forward(np.array([bench_by_date.get(str(x), np.nan) for x in dates], dtype=float))
    else:
        bench = market_proxy(close, value)
    return Panel(dates=dates, keys=keys, close=close, value=value, bench=bench)


def _fill_forward(a: np.ndarray) -> np.ndarray:
    a = a.copy()
    for i in range(1, len(a)):
        if np.isnan(a[i]):
            a[i] = a[i - 1]
    return a
