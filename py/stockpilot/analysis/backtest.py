"""Base rates from history: how often stocks beat the Nifty 50 over the horizon by more than their round-trip costs plus tax
on the gain (the hurdle, `costs.py`), in 40 buckets: momentum (5) x regime (2) x volatility (calm or jumpy) x liquidity
(large or small). Only price factors can be tested this way: free sources keep no point-in-time fundamentals, so quality and
value stay untested (stated on the dashboard)."""
from datetime import date, timedelta
from itertools import product
from pathlib import Path
from statistics import median

import duckdb

from stockpilot import costs, journal

from stockpilot.analysis import analytics, tax
from stockpilot.analysis.screen import _percentiles

MIN_DAYS = 200
LARGE_CR = 20.0              # a day's traded value above this is "large", at or below it "small"
TRADE_VALUE = 100_000        # the position the hurdle is costed on (the flat depository fee weighs on a small one)
NIFTY_3M = 0.03              # the index's assumed 3-month gain in the hurdle, as in config `rules.nifty_3m`
REGIMES = ("nifty_up", "nifty_down")
ALL_BUCKETS = [(m, r, v, l) for m, r, v, l in product(range(5), REGIMES, ("calm", "jumpy"), ("large", "small"))]


def cut_of(vol: float | None, median_vol: float | None, adv_cr: float | None) -> tuple[str, str]:
    """(calm|jumpy, large|small): jumpy is above the median 1-year volatility, large is above ₹20 crore a day."""
    jumpy = vol is not None and median_vol is not None and vol > median_vol
    return ("jumpy" if jumpy else "calm", "large" if (adv_cr or 0) > LARGE_CR else "small")


def _momentum_buckets(factors: dict, buckets: int, floor_cr: float) -> dict[str, int]:
    pool = {s: f for s, f in factors.items() if f["days"] >= MIN_DAYS and (f["adv_3m_cr"] or 0) >= floor_cr}
    parts = []
    for metric in ("ret_12m", "ret_6m", "dist_200dma"):
        vals = {s: f[metric] for s, f in pool.items() if f[metric] is not None}
        parts.append(_percentiles(vals, True) if vals else {})
    score = {s: sum(p.get(s, 0.5) for p in parts) / len(parts) for s in pool}
    ranked = sorted(score, key=score.get)
    return {s: min(buckets - 1, i * buckets // len(ranked)) for i, s in enumerate(ranked)}


# One pass over the whole history, whatever the number of steps. A ratio of two split-adjusted closes is
# the same whichever later factors are applied, so a single adjusted table serves every step.
ADJ_TABLE_SQL = """
create or replace temp table bt_adj as
with a as ({adjusted})
select a.symbol, a.exchange, a.date, a.adj_close, p.value,
       row_number() over (partition by a.symbol, a.exchange order by a.date) as idx,
       a.adj_close / lag(a.adj_close) over (partition by a.symbol, a.exchange order by a.date) - 1 as ret
from a join prices p using (symbol, exchange, date)
"""

# Rolling windows per row (row -126, row -252, 200-row mean, 63-row mean value, 1-year volatility of daily returns); a step
# reads the row it lands on.
ROLL_TABLE_SQL = """
create or replace temp table bt_roll as
select symbol, exchange, idx, adj_close,
       lag(adj_close, 126) over w as adj_126, lag(adj_close, 252) over w as adj_252,
       avg(adj_close) over (partition by symbol, exchange order by idx rows between 199 preceding and current row) as ma_200,
       avg(value) over (partition by symbol, exchange order by idx rows between 62 preceding and current row) as adv_63,
       stddev_samp(ret) over (partition by symbol, exchange order by idx rows between 251 preceding and current row) as vol_252
from bt_adj window w as (partition by symbol, exchange order by idx)
"""

STEPS_SQL = """
create or replace temp table bt_steps as
select k, $start::date + (k * $step)::int as day, $start::date + (k * $step + $horizon)::int as exit_day,
       $start::date + (k * $step - $lookback)::int as since
from range($n::bigint) t(k)
"""

# Per step and stock: the last row on/before the step inside the lookback, the first row in it, and the row count.
FACTORS_SQL = """
with w as (
    select s.k, a.symbol, a.exchange, max(a.idx) as last_idx, min(a.idx) as first_idx
    from bt_steps s join bt_adj a on a.date between s.since and s.day
    group by s.k, a.symbol, a.exchange
)
select w.k, w.symbol, w.exchange,
       case when w.last_idx - 126 >= w.first_idx then r.adj_close / r.adj_126 - 1 end as ret_6m,
       case when w.last_idx - 252 >= w.first_idx then r.adj_close / r.adj_252 - 1 end as ret_12m,
       r.adj_close / r.ma_200 - 1 as dist_200dma,
       r.adv_63 / 1e7 as adv_3m_cr,
       r.vol_252 as vol_1y,
       least(253, w.last_idx - w.first_idx + 1) as days
from w join bt_roll r on r.symbol = w.symbol and r.exchange = w.exchange and r.idx = w.last_idx
order by w.k, w.symbol, w.exchange
"""

# Steps whose entry row lies within DEMERGER_SKIP_DAYS trading days of a demerger's ex-date: a demerger's price
# factor is a one-day estimate, so the windows around it are left out of the base rates.
DEMERGER_SKIP_DAYS = 20
DEMERGER_STEPS_SQL = """
with d as (
    select c.symbol, a.exchange, min(a.idx) as ex_idx
    from corporate_actions c join bt_adj a on a.symbol = c.symbol and a.date >= c.ex_date
    where c.kind = 'demerger' group by c.symbol, c.ex_date, a.exchange
), w as (
    select s.k, a.symbol, a.exchange, max(a.idx) as last_idx
    from bt_steps s join bt_adj a on a.date between s.since and s.day group by s.k, a.symbol, a.exchange
)
select distinct w.k, w.symbol, w.exchange from w join d using (symbol, exchange)
where w.last_idx between d.ex_idx - $n and d.ex_idx + $n
"""

# Entry = first close on/after the step, exit = last close on/before step + horizon.
FORWARD_SQL = """
select s.k, a.symbol, a.exchange, arg_max(a.adj_close, a.idx) / arg_min(a.adj_close, a.idx) - 1 as ret
from bt_steps s join bt_adj a on a.date between s.day and s.exit_day
group by s.k, a.symbol, a.exchange
"""

NIFTY_SQL = """
create or replace temp table bt_nifty as
select date, close, row_number() over (order by date) as idx,
       avg(close) over (order by date rows between 199 preceding and current row) as ma_200
from index_levels where name = 'Nifty 50'
"""

NIFTY_STEPS_SQL = """
select s.k,
       arg_max(n.close, n.date) filter (where n.date <= s.day) as close_now,
       arg_max(n.ma_200, n.date) filter (where n.date <= s.day) as ma_now,
       arg_max(n.close, n.date) filter (where n.date <= s.exit_day) as close_exit
from bt_steps s join bt_nifty n on n.date <= s.exit_day
group by s.k
"""


def _db_dir(db) -> Path | None:
    for _, _, file in db.execute("pragma database_list").fetchall():
        if file:
            return Path(file).parent
    return None


def _cap_memory(db) -> str:
    """Cap DuckDB at 300 MB, spilling to `<data dir>/duckdb_tmp`, so the 1 GB VM is not exhausted."""
    previous = db.execute("select current_setting('memory_limit')").fetchone()[0]
    db.execute("set memory_limit = '300MB'")
    folder = _db_dir(db)
    if folder is not None:
        tmp = folder / "duckdb_tmp"
        tmp.mkdir(parents=True, exist_ok=True)
        db.execute(f"set temp_directory = '{tmp}'")
    return previous


def base_rates(db: duckdb.DuckDBPyConnection, start: date, end: date, horizon_days: int = 91,
               step_days: int = 28, buckets: int = 5, floor_cr: float = 1.0, lookback_days: int = 400,
               trade_value: float = TRADE_VALUE, nifty_3m: float = NIFTY_3M, tax_rate: float | None = None) -> dict:
    """Same result as running the price factors and forward returns once per step, in a fixed number of
    queries. Stocks whose scores tie are bucketed in symbol order (the per-step version left it to row order).
    Returns {(momentum, regime, vol, liquidity): {n, hit_rate, avg_excess}}. A hit is an excess over the Nifty above the
    stock's hurdle (round-trip costs at its liquidity plus tax on the gain), not the raw beat; `avg_excess` is the raw excess."""
    rate = tax.rules_for(tax.fy_of(date.today())).stcg_equity_rate if tax_rate is None else tax_rate
    n_steps = (end - start).days // step_days + 1 if end >= start else 0
    if n_steps == 0:
        return {}
    previous_limit = _cap_memory(db)
    try:
        db.execute(ADJ_TABLE_SQL.format(adjusted=analytics.ADJUSTED_SQL.format(symbol_filter="")),
                   {"since": date(1900, 1, 1)})
        db.execute(ROLL_TABLE_SQL)
        db.execute(STEPS_SQL, {"start": start, "step": step_days, "horizon": horizon_days,
                               "lookback": lookback_days, "n": n_steps})
        db.execute(NIFTY_SQL)
        nifty = {k: (now, ma, out) for k, now, ma, out in db.execute(NIFTY_STEPS_SQL).fetchall()}
        factor_rows = db.execute(FACTORS_SQL).fetchall()
        near_demerger = set(db.execute(DEMERGER_STEPS_SQL, {"n": DEMERGER_SKIP_DAYS}).fetchall())
        forward_rows = db.execute(FORWARD_SQL).fetchall()
    finally:
        db.execute(f"set memory_limit = '{previous_limit}'")

    factors: dict[int, dict[str, dict]] = {}
    for k, symbol, exchange, ret_6m, ret_12m, dist, adv, vol, days in factor_rows:     # sorted by step, symbol
        if (k, symbol, exchange) in near_demerger:
            continue
        per_step = factors.setdefault(k, {})
        if symbol not in per_step or (exchange == "NSE" and per_step[symbol]["exchange"] != "NSE"):
            per_step[symbol] = {"exchange": exchange, "ret_6m": ret_6m, "ret_12m": ret_12m,
                                "dist_200dma": dist, "adv_3m_cr": adv, "vol_1y": vol, "days": days}
    forward: dict[int, dict[tuple[str, str], float]] = {}
    for k, symbol, exchange, ret in forward_rows:
        forward.setdefault(k, {})[(symbol, exchange)] = ret

    tally: dict[tuple, list[float]] = {}
    for k in range(n_steps):
        now, ma, then = nifty.get(k, (None, None, None))
        if not (now and then):
            continue
        nifty_ret = then / now - 1
        regime = "nifty_up" if now >= ma else "nifty_down"
        step_factors = factors.get(k, {})
        members = _momentum_buckets(step_factors, buckets, floor_cr)
        vols = [step_factors[s]["vol_1y"] for s in members if step_factors[s]["vol_1y"] is not None]
        median_vol = median(vols) if vols else None
        for symbol, bucket in members.items():
            f = step_factors[symbol]
            ret = forward.get(k, {}).get((symbol, f["exchange"]))
            if ret is not None:
                hurdle = costs.hurdle(costs.round_trip(trade_value, f["adv_3m_cr"])["pct"], nifty_3m, rate)
                calm, size = cut_of(f["vol_1y"], median_vol, f["adv_3m_cr"])
                tally.setdefault((bucket, regime, calm, size), []).append((ret - nifty_ret, hurdle))
    return {key: {"n": len(v), "hit_rate": sum(e > h for e, h in v) / len(v), "avg_excess": sum(e for e, _ in v) / len(v)}
            for key, v in tally.items()}


def save(db: duckdb.DuckDBPyConnection, rates: dict, horizon_days: int, computed_on: date) -> None:
    """Store the 40-bucket table, and the older momentum x regime table summed over volatility and liquidity so
    readiness and any reader of it keep working. One transaction: a reader never sees one table without the other."""
    coarse: dict[tuple, list[float]] = {}
    for (bucket, regime, _vol, _liq), v in rates.items():
        c = coarse.setdefault((bucket, regime), [0, 0.0, 0.0])
        c[0] += v["n"]
        c[1] += v["hit_rate"] * v["n"]
        c[2] += v["avg_excess"] * v["n"]
    db.execute("begin")
    try:
        db.execute("delete from base_rate_buckets where horizon_days = ?", [horizon_days])
        db.executemany("insert into base_rate_buckets values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                       [(horizon_days, b, r, vol, liq, v["n"], v["hit_rate"], v["avg_excess"], computed_on)
                        for (b, r, vol, liq), v in rates.items()])
        db.execute("delete from base_rates where horizon_days = ?", [horizon_days])
        db.executemany("insert into base_rates values ('momentum', ?, ?, ?, ?, ?, ?, ?)",
                       [(b, r, horizon_days, n, hits / n, excess / n, computed_on)
                        for (b, r), (n, hits, excess) in coarse.items() if n])
        db.execute("commit")
    except Exception:
        db.execute("rollback")
        raise


def monthly(db: duckdb.DuckDBPyConnection, today: date, start: date = date(2016, 1, 1), horizon_days: int = 91,
            step_days: int = 28) -> dict:
    """The first-Sunday job: the whole history up to the last priced day (less the horizon, so every step has its outcome),
    stored. One `runs` row named `base_rates`. R2's `jobs/base_rates.py` calls this."""
    with journal.run(db, "base_rates") as r:
        last = db.execute("select max(date) from prices").fetchone()[0]
        if last is None:
            r.status = "skipped"
            r.notes["note"] = "No prices are stored, so no base rates were computed."
            return r.notes
        end = min(today, last) - timedelta(days=horizon_days)
        rates = base_rates(db, start, end, horizon_days=horizon_days, step_days=step_days)
        save(db, rates, horizon_days, today)
        r.notes.update({"buckets": len(rates), "samples": sum(v["n"] for v in rates.values()), "through": str(end)})
        return r.notes
