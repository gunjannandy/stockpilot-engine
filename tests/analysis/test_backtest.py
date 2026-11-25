from datetime import date, timedelta

from helpers import insert_prices
from stockpilot import store
from stockpilot.analysis import backtest

START = date(2024, 1, 1)


def series(symbol, growth, days=420, value=3e7):
    rows, prev = [], 100.0
    for i in range(days):
        close = 100 * (1 + growth) ** i
        rows.append((START + timedelta(i), symbol, "NSE", "EQ", close, close, close, close, prev, 1000, value, 10))
        prev = close
    return rows


def agg(rates, bucket, regime="nifty_up"):
    """Pool one momentum bucket's rows over the volatility and liquidity cuts."""
    rows = [v for (b, r, _vol, _liq), v in rates.items() if b == bucket and r == regime]
    n = sum(v["n"] for v in rows)
    return {"n": n, "hit_rate": sum(v["hit_rate"] * v["n"] for v in rows) / n,
            "avg_excess": sum(v["avg_excess"] * v["n"] for v in rows) / n}


def flat_nifty(db, days=420):
    for i in range(days):
        db.execute("insert into index_levels values (?, 'Nifty 50', 20000, 20, 3, 1)", [START + timedelta(i)])


def test_rising_stocks_beat_a_flat_nifty_and_falling_ones_do_not(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    rows = []
    for i in range(5):
        rows += series(f"UP{i}", 0.002)
        rows += series(f"DN{i}", -0.002)
    insert_prices(db, rows)
    flat_nifty(db)
    rates = backtest.base_rates(db, START + timedelta(260), START + timedelta(380),
                                horizon_days=30, step_days=30, buckets=2)
    top, bottom = agg(rates, 1), agg(rates, 0)
    assert top["hit_rate"] == 1.0 and bottom["hit_rate"] == 0.0
    assert top["n"] == 5 * 5                     # 5 stocks on each of 5 dates
    assert top["avg_excess"] > 0


def test_the_outcome_is_beating_the_nifty_by_more_than_the_hurdle_not_the_raw_beat(tmp_path):
    """A stock 0.6% ahead of the Nifty in a month beats it, but not by the roughly 1.5% that costs and tax need."""
    db = store.open(tmp_path / "sp.duckdb")
    rows = []
    for i in range(5):
        rows += series(f"SLOW{i}", 0.0002)       # about +0.6% over 30 days: ahead of a flat Nifty, short of the hurdle
        rows += series(f"FAST{i}", 0.002)        # about +6%
    insert_prices(db, rows)
    flat_nifty(db)
    rates = backtest.base_rates(db, START + timedelta(260), START + timedelta(380),
                                horizon_days=30, step_days=30, buckets=2)
    slow, fast = agg(rates, 0), agg(rates, 1)
    assert slow["avg_excess"] > 0 and slow["hit_rate"] == 0.0     # raw beat, but under the hurdle
    assert fast["hit_rate"] == 1.0


def test_there_are_forty_buckets_and_every_row_lands_in_one(tmp_path):
    assert len(backtest.ALL_BUCKETS) == 40
    assert {b for b, _r, _v, _l in backtest.ALL_BUCKETS} == set(range(5))
    assert {r for _b, r, _v, _l in backtest.ALL_BUCKETS} == {"nifty_up", "nifty_down"}
    assert {v for _b, _r, v, _l in backtest.ALL_BUCKETS} == {"calm", "jumpy"}
    assert {l for _b, _r, _v, l in backtest.ALL_BUCKETS} == {"large", "small"}
    db = store.open(tmp_path / "sp.duckdb")
    dates = random_market(db, 60, 800, seed=3, large=set(f"S{s:03d}" for s in range(0, 60, 2)))
    got = backtest.base_rates(db, dates[300], dates[700], horizon_days=91, step_days=28)
    assert got and set(got) <= set(backtest.ALL_BUCKETS)
    assert {v for _b, _r, v, _l in got} == {"calm", "jumpy"} and {l for _b, _r, _v, l in got} == {"large", "small"}
    backtest.save(db, got, 91, date(2026, 8, 21))
    stored = db.execute("select count(*), sum(n) from base_rate_buckets where horizon_days = 91").fetchone()
    assert stored == (len(got), sum(v["n"] for v in got.values()))
    # the older momentum x regime table is kept in step with it, so readiness and the old lookup still work
    old = db.execute("select sum(n) from base_rates where horizon_days = 91").fetchone()[0]
    assert old == stored[1]


def test_calm_is_at_or_below_the_median_volatility_and_large_is_above_20_crore():
    assert backtest.cut_of(vol=0.20, median_vol=0.25, adv_cr=30.0) == ("calm", "large")
    assert backtest.cut_of(vol=0.25, median_vol=0.25, adv_cr=20.0) == ("calm", "small")
    assert backtest.cut_of(vol=0.40, median_vol=0.25, adv_cr=5.0) == ("jumpy", "small")


# ---- lane G: the fast backtest must equal the slow one, in a fixed number of queries ----
import time

import numpy as np
import pandas as pd

from helpers import PRICE_COLS
from stockpilot.analysis import analytics
from stockpilot.analysis.screen import _percentiles  # noqa: F401  (the reference uses backtest._momentum_buckets)


def reference_base_rates(db, start, end, horizon_days=91, step_days=28, buckets=5, floor_cr=1.0,
                         trade_value=100_000, nifty_3m=0.03):
    """The step-by-step implementation this lane replaced, kept as the oracle."""
    def nifty_on(day):
        row = db.execute("select close from index_levels where name = 'Nifty 50' and date <= ? "
                         "order by date desc limit 1", [day]).fetchone()
        return row[0] if row else None

    def regime(day):
        closes = [c for (c,) in db.execute("select close from index_levels where name = 'Nifty 50' and date <= ? "
                                           "order by date desc limit 200", [day]).fetchall()]
        if not closes:
            return "unknown"
        return "nifty_up" if closes[0] >= sum(closes) / len(closes) else "nifty_down"

    def forward(day, exit_day):
        sql = ("with a as ({adj}) select symbol, exchange, arg_min(adj_close, date) as entry, "
               "arg_max(adj_close, date) as exit from a where date <= $exit_day group by symbol, exchange"
               ).format(adj=analytics.ADJUSTED_SQL.format(symbol_filter=""))
        rows = db.execute(sql, {"since": day, "exit_day": exit_day}).fetchall()
        return {(s, e): x / n - 1 for s, e, n, x in rows if n}

    from statistics import median, stdev
    from stockpilot import costs
    from stockpilot.analysis import tax
    rate = tax.rules_for(tax.fy_of(date.today())).stcg_equity_rate
    adj = {}
    for symbol, exchange, d, c in db.execute(
            "with a as ({adj}) select symbol, exchange, date, adj_close from a order by symbol, exchange, date".format(
                adj=analytics.ADJUSTED_SQL.format(symbol_filter="")), {"since": date(1900, 1, 1)}).fetchall():
        adj.setdefault((symbol, exchange), []).append((d, c))

    def vol(symbol, exchange, day):
        closes = [c for d, c in adj[(symbol, exchange)] if d <= day][-253:]
        rets = [b / a - 1 for a, b in zip(closes, closes[1:])]
        return stdev(rets)

    tally = {}
    day = start
    while day <= end:
        exit_day = day + timedelta(horizon_days)
        now, then = nifty_on(day), nifty_on(exit_day)
        if now and then:
            nifty_ret = then / now - 1
            factors = analytics.price_factors(db, day)
            fwd = forward(day, exit_day)
            reg = regime(day)
            factors = dict(sorted(factors.items()))     # score ties break by symbol, not by DuckDB row order
            members = backtest._momentum_buckets(factors, buckets, floor_cr)
            vols = {s: vol(s, factors[s]["exchange"], day) for s in members}
            med = median(vols.values()) if vols else None
            for symbol, bucket in members.items():
                ret = fwd.get((symbol, factors[symbol]["exchange"]))
                if ret is not None:
                    adv = factors[symbol]["adv_3m_cr"]
                    hurdle = costs.hurdle(costs.round_trip(trade_value, adv)["pct"], nifty_3m, rate)
                    calm, size = backtest.cut_of(vols[symbol], med, adv)
                    tally.setdefault((bucket, reg, calm, size), []).append((ret - nifty_ret, hurdle))
        day += timedelta(step_days)
    return {k: {"n": len(v), "hit_rate": sum(e > h for e, h in v) / len(v), "avg_excess": sum(e for e, _ in v) / len(v)}
            for k, v in tally.items()}


def random_market(db, n_stocks, n_days, seed=1, splits=(), late=(), thin=(), bse=(), large=()):
    """Random-walk prices on weekdays, a Nifty that wanders, optional splits {symbol: day_index}."""
    rng = np.random.default_rng(seed)
    dates = [d for d in (START + timedelta(i) for i in range(int(n_days * 7 / 5) + 10)) if d.weekday() < 5][:n_days]
    frames, split_days = [], []
    for s in range(n_stocks):
        sym = f"S{s:03d}"
        first = late_start(sym, late)
        drift = rng.normal(0.0004, 0.0015)
        rets = rng.normal(drift, 0.015, n_days)
        close = 100 * np.exp(np.cumsum(rets))
        prev = np.concatenate([[100.0], close[:-1]]).copy()
        if sym in splits:
            k = splits[sym]
            close[k:] = close[k:] / 2
            prev[k] = prev[k] / 2
            split_days.append((sym, k))
        value = np.full(n_days, 0.2e7 if sym in thin else 5e8 if sym in large else 3e7) * rng.uniform(0.8, 1.2, n_days)
        df = pd.DataFrame({"date": dates, "symbol": sym, "exchange": "BSE" if sym in bse else "NSE",
                           "series": "EQ", "open": close, "high": close, "low": close, "close": close,
                           "prev_close": prev, "volume": 1000, "value": value, "trades": 10})
        frames.append(df.iloc[first:])
    all_rows = pd.concat(frames)[PRICE_COLS]
    for sym, k in split_days:
        db.execute("insert into corporate_actions (symbol, ex_date, kind, numerator, denominator) "
                   "values (?, ?, 'split', 2, 1)", [sym, dates[k]])
    db.register("_m", all_rows)
    db.execute("insert into prices select * from _m")
    db.unregister("_m")
    nifty = 20000 * np.exp(np.cumsum(rng.normal(0.0003, 0.008, n_days)))
    idx = pd.DataFrame({"date": dates, "name": "Nifty 50", "close": nifty, "pe": 20.0, "pb": 3.0, "dy": 1.0})
    db.register("_i", idx)
    db.execute("insert into index_levels select * from _i")
    db.unregister("_i")
    return dates


def late_start(sym, late):
    return late.get(sym, 0) if isinstance(late, dict) else 0


def test_fast_backtest_equals_the_step_by_step_one_with_splits_gaps_and_thin_stocks(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    dates = random_market(db, 40, 700, splits={"S003": 450, "S010": 300}, late={"S020": 200, "S021": 420},
                          thin={"S030", "S031"}, bse={"S035", "S036"}, large={f"S{s:03d}" for s in range(0, 40, 3)})
    start, end = dates[300], dates[650]
    args = dict(horizon_days=91, step_days=28, buckets=5, floor_cr=1.0)
    want = reference_base_rates(db, start, end, **args)
    got = backtest.base_rates(db, start, end, **args)
    assert any(liq == "large" for _b, _r, _v, liq in want) and any(v == "jumpy" for _b, _r, v, _l in want)
    assert want and got.keys() == want.keys()
    for k, w in want.items():
        assert got[k]["n"] == w["n"], k
        assert abs(got[k]["hit_rate"] - w["hit_rate"]) < 1e-9, k
        assert abs(got[k]["avg_excess"] - w["avg_excess"]) < 1e-9, k


class CountingDb:
    """Wraps a DuckDB connection and counts `execute` calls."""
    def __init__(self, db):
        self._db, self.executes = db, 0

    def execute(self, *a, **kw):
        self.executes += 1
        return self._db.execute(*a, **kw)

    def __getattr__(self, name):
        return getattr(self._db, name)


def test_the_number_of_queries_does_not_depend_on_the_number_of_steps(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    dates = random_market(db, 12, 600)
    counts = []
    for steps in (3, 30):
        wrapped = CountingDb(db)
        backtest.base_rates(wrapped, dates[250], dates[250] + timedelta(28 * (steps - 1)),
                            horizon_days=60, step_days=28, buckets=3)
        counts.append(wrapped.executes)
    assert counts[0] == counts[1]


def test_300_stocks_over_1500_days_run_50_steps_in_under_a_minute(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    dates = random_market(db, 300, 1500, seed=7)
    start = dates[400]
    t0 = time.time()
    rates = backtest.base_rates(db, start, start + timedelta(28 * 49), horizon_days=91, step_days=28)
    elapsed = time.time() - t0
    print(f"synthetic timing: 300 stocks x 1500 days x 50 steps = {elapsed:.1f}s")
    assert rates and elapsed < 60
