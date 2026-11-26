"""Training rows, walk-forward testing and the range, for one horizon.

A training row is one stock on one start day (a month apart, so rows overlap less than daily ones would). Its outcome is
whether the stock beat the benchmark by more than the cost hurdle over the next `h` trading days. Testing is walk-forward
with a purge gap: a fold may train only on rows whose outcome was known `h` days before its first test day. The range is
the empirical 10th/90th percentile of volatility-normalised returns of similar setups, widened or narrowed by adaptive
conformal steps so the band's observed coverage tracks its 80% target."""
from dataclasses import dataclass

import numpy as np

from stockpilot.mechanical import model, signals

STEP = 21                    # days between start days
HURDLE = 0.01                # beat the benchmark by this much over the horizon (round-trip cost and tax allowance)
FEATURES = ["momentum", "mom12", "near_52w_high", "low_volatility", "trend", "market_regime", "regime_x_momentum"]
INFO_ONLY = ["delivery_info", "reversal_1m_info"]
TARGET = 0.8                 # the band should hold this share of outcomes
ACI_GAMMA = 0.05             # one step per start day (monthly), so larger than the daily-data 0.005-0.02
MIN_FIT_ROWS = 300
N_BUCKETS = 5 * 2 * 2 * 2
FIRST_DAY = 252              # 12-1 momentum needs a year of closes


@dataclass
class Rows:
    t: np.ndarray
    stock: np.ndarray
    X: np.ndarray
    bucket: np.ndarray
    vol: np.ndarray
    rev: np.ndarray
    y: np.ndarray | None = None
    ret: np.ndarray | None = None


def rows_at(panel, t: int, extras=None) -> Rows | None:
    """Model inputs for every stock with full signals on day t (no outcomes)."""
    s = signals.compute(panel, t, extras)
    r = signals.raw(panel, t)
    mom = s["momentum"]
    cols = {"momentum": mom, "mom12": signals.rank01(r["mom12"]), "near_52w_high": s["near_52w_high"],
            "low_volatility": s["low_volatility"], "trend": s["trend"], "market_regime": s["market_regime"],
            "regime_x_momentum": s["market_regime"] * (mom - 0.5)}
    X = np.column_stack([cols[f] for f in FEATURES])
    ok = np.isfinite(X).all(axis=1) & np.isfinite(r["vol"]) & (r["vol"] > 0) & np.isfinite(s["liquidity"])
    idx = np.flatnonzero(ok)
    if not len(idx):
        return None
    q = np.minimum((mom[idx] * 5).astype(int), 4)
    bucket = ((q * 2 + s["market_regime"][idx].astype(int)) * 2 + (s["low_volatility"][idx] >= 0.5)) * 2 \
        + (s["liquidity"][idx] >= 0.5)
    return Rows(np.full(len(idx), t), idx, X[idx], bucket.astype(int), r["vol"][idx], r["ret21"][idx])


def build_dataset(panel, h: int, step: int = STEP) -> Rows:
    parts = []
    for t in range(FIRST_DAY, panel.n_days - h, step):
        rows = rows_at(panel, t)
        if rows is None:
            continue
        end = panel.close[t + h, rows.stock]
        ret = end / panel.close[t, rows.stock] - 1
        bench = panel.bench[t + h] / panel.bench[t] - 1
        keep = np.isfinite(ret)          # a stock gone by t+h has no outcome here: noted as survivorship in the report
        rows.y = (ret - bench > HURDLE).astype(float)
        rows.ret = ret
        parts.append(_take(rows, keep))
    return _cat(parts)


def _take(r: Rows, m) -> Rows:
    return Rows(*(None if a is None else a[m] for a in (r.t, r.stock, r.X, r.bucket, r.vol, r.rev, r.y, r.ret)))


def _cat(parts: list) -> Rows:
    return Rows(*[np.concatenate([getattr(p, f) for p in parts]) for f in ("t", "stock", "X", "bucket", "vol", "rev", "y", "ret")])


# ---- models ------------------------------------------------------------------------------------------------------

@dataclass
class Fitted:
    h: int
    parent: float
    rates: np.ndarray
    logistic: model.Logistic
    platt: model.Platt
    z_all: np.ndarray
    z_bucket: dict

    def chance(self, X, bucket):
        base = self.rates[bucket]
        lg = self.logistic.predict(X)
        bl = model.blend(base, lg)
        return {"base": base, "logistic": lg, "blend": bl, "final": self.platt.apply(bl)}

    def band(self, rows: Rows, alpha: float):
        """(low, likely, high) returns for the rows, from normalised quantiles scaled by each stock's own volatility."""
        scale = rows.vol * np.sqrt(self.h)
        qs = np.empty((len(rows.t), 3))
        for b in np.unique(rows.bucket):
            z = self.z_bucket.get(int(b), self.z_all)
            qs[rows.bucket == b] = np.quantile(z, [alpha / 2, 0.5, 1 - alpha / 2])
        return qs * scale[:, None]


def fit(rows: Rows, h: int, cal_share: float = 0.25) -> Fitted | None:
    """Fit on early start days, calibrate (Platt) on the latest ones; both use only rows whose outcome is known."""
    days = np.unique(rows.t)
    cal_start = days[int(len(days) * (1 - cal_share))]
    fit_m = rows.t + 2 * h <= cal_start
    cal_m = rows.t >= cal_start
    if fit_m.sum() < MIN_FIT_ROWS or cal_m.sum() < 50:
        return None
    overlap = h / STEP
    y = rows.y
    parent = y[fit_m].mean()
    n = np.bincount(rows.bucket[fit_m], minlength=N_BUCKETS)
    hits = np.bincount(rows.bucket[fit_m], weights=y[fit_m], minlength=N_BUCKETS)
    rates = np.array([model.smoothed_rate(hits[b], n[b], parent, overlap) for b in range(N_BUCKETS)])
    logistic = model.fit_logistic(rows.X[fit_m], y[fit_m], l2=5.0)
    bl = model.blend(rates[rows.bucket[cal_m]], logistic.predict(rows.X[cal_m]))
    platt = model.fit_platt(bl, y[cal_m])
    z = rows.ret / (rows.vol * np.sqrt(h))
    z_bucket = {b: z[rows.bucket == b] for b in range(N_BUCKETS) if (rows.bucket == b).sum() >= 100}
    return Fitted(h, parent, rates, logistic, platt, z, z_bucket)


# ---- walk-forward -------------------------------------------------------------------------------------------------

def _brier(p, y):
    return float(np.mean((p - y) ** 2))


def walk_forward(panel, h: int, n_folds: int = 5, ds: Rows | None = None) -> dict:
    ds = ds if ds is not None else build_dataset(panel, h)
    days = np.unique(ds.t)
    blocks = np.array_split(days[int(len(days) * 0.4):], n_folds)
    preds = {k: [] for k in ("base", "logistic", "blend", "final")}
    ys, parents, revs, covered, folds = [], [], [], [], []
    alpha, pending = 1 - TARGET, []
    for block in blocks:
        if not len(block):
            continue
        first = block[0]
        train = _take(ds, ds.t + 2 * h <= first)       # outcome known h days before the test starts, plus an h-day purge gap
        f = fit(train, h) if len(train.t) else None
        if f is None:
            continue
        test = _take(ds, np.isin(ds.t, block))
        c = f.chance(test.X, test.bucket)
        for k in preds:
            preds[k].append(c[k])
        ys.append(test.y)
        parents.append(np.full(len(test.y), f.parent))
        revs.append(test.rev)
        for d in block:
            for resolve, miss in [p for p in pending if p[0] <= d]:
                alpha = float(np.clip(alpha + ACI_GAMMA * ((1 - TARGET) - miss), 0.02, 0.6))
            pending = [p for p in pending if p[0] > d]
            m = test.t == d
            if not m.any():
                continue
            sub = _take(test, m)
            lo, _, hi = f.band(sub, alpha).T
            inside = (sub.ret >= lo) & (sub.ret <= hi)
            covered.append(inside)
            pending.append((int(d) + h, 1 - float(inside.mean())))
        folds.append({"train_last_start": int(train.t.max()), "test_first_start": int(first), "n_train": int(len(train.t)),
                      "n_test": int(len(test.y)), "brier": _brier(c["final"], test.y)})
    if not ys:
        return {"horizon_days": h, "n_test": 0, "folds": []}
    y = np.concatenate(ys)
    P = {k: np.concatenate(v) for k, v in preds.items()}
    cov = np.concatenate(covered)
    rev = np.concatenate(revs)
    lo3, hi3 = np.quantile(rev, [1 / 3, 2 / 3])
    return {
        "horizon_days": h, "n_test": int(len(y)), "folds": folds, "hurdle": HURDLE,
        "hit_rate": float(y.mean()),
        "brier": {"final": _brier(P["final"], y), "base_rate_alone": _brier(np.concatenate(parents), y),
                  "always_50": _brier(np.full(len(y), 0.5), y), "bucket": _brier(P["base"], y),
                  "logistic": _brier(P["logistic"], y), "blend_uncalibrated": _brier(P["blend"], y)},
        "calibration": _bins(P["final"], y),
        "coverage": {"target": TARGET, "observed": float(cov.mean()), "n": int(len(cov)), "alpha_final": alpha},
        "information_only": INFO_ONLY,
        "reversal_check": {"low_third_hit_rate": float(y[rev <= lo3].mean()), "high_third_hit_rate": float(y[rev >= hi3].mean())},
        "survivorship": "stocks gone by the end of the horizon have no outcome and are left out; bucket rates for weak "
                        "momentum may read kind",
    }


def _bins(p, y):
    out = []
    edges = np.linspace(0, 1, 11)
    for a, b in zip(edges[:-1], edges[1:]):
        m = (p >= a) & ((p < b) if b < 1 else (p <= b))
        if m.any():
            out.append({"bin": f"{a:.1f}-{b:.1f}", "predicted": float(p[m].mean()), "actual": float(y[m].mean()), "n": int(m.sum())})
    return out
