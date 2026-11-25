"""Price analytics over the store. Bhavcopy prices are unadjusted. The only source of adjustment is the
`corporate_actions` table: a split is worth numerator / denominator, a bonus (numerator + denominator) /
denominator, a demerger its `price_factor` (the ex-date jump, derived from prices), several actions on one day multiply, and a close is divided by every factor whose ex-date is
after it. A price jump with no action stays a jump: a real crash must not be adjusted away."""
from datetime import date

import duckdb

ADJUSTED_SQL = """
with p as (
    select symbol, exchange, date, close from prices where date >= $since {symbol_filter}
), a as (
    select symbol, ex_date, sum(ln(factor)) as log_factor from (
        select symbol, ex_date, case kind when 'split' then numerator / denominator
                                          else (numerator + denominator) / denominator end as factor
        from corporate_actions where kind in ('split', 'bonus') and numerator > 0 and denominator > 0
        union all
        select symbol, ex_date, price_factor from demerger_factors where price_factor > 0)
    group by symbol, ex_date
)
select p.symbol, p.exchange, p.date, p.close / coalesce(exp(sum(a.log_factor)), 1) as adj_close
from p left join a on a.symbol = p.symbol and a.ex_date > p.date
group by p.symbol, p.exchange, p.date, p.close
"""


def adjusted_closes(db: duckdb.DuckDBPyConnection, symbol: str, since: date, exchange: str = "NSE"):
    sql = ADJUSTED_SQL.format(symbol_filter="and symbol = $symbol and exchange = $exchange")
    return db.execute(f"select date, adj_close from ({sql}) order by date",
                      {"since": since, "symbol": symbol, "exchange": exchange}).fetchall()


def adjusted_closes_many(db: duckdb.DuckDBPyConnection, symbols, since: date, exchange: str = "NSE") -> dict[str, list]:
    """`adjusted_closes` for many symbols in one query: {symbol: [(date, adj_close), ...]} oldest first."""
    symbols = sorted(set(symbols))
    if not symbols:
        return {}
    sql = ADJUSTED_SQL.format(symbol_filter="and exchange = $exchange and symbol in (select unnest($symbols))")
    out: dict[str, list] = {s: [] for s in symbols}
    for symbol, day, close in db.execute(f"select symbol, date, adj_close from ({sql}) order by symbol, date",
                                         {"since": since, "symbols": symbols, "exchange": exchange}).fetchall():
        out[symbol].append((day, close))
    return out


FACTORS_SQL = """
with a as ({adjusted}),
w as (
    select a.*, p.value,
           row_number() over (partition by a.symbol, a.exchange order by a.date desc) as rn
    from a join prices p using (symbol, exchange, date)
    where a.date <= $as_of
),
r as (
    select *, adj_close / lead(adj_close) over (partition by symbol, exchange order by date desc) - 1 as ret
    from w where rn <= 253
)
select symbol, exchange,
    max(adj_close) filter (where rn = 1) as close,
    max(adj_close) filter (where rn = 1) / max(adj_close) filter (where rn = 127) - 1 as ret_6m,
    max(adj_close) filter (where rn = 1) / max(adj_close) filter (where rn = 253) - 1 as ret_12m,
    max(adj_close) filter (where rn = 1) / avg(adj_close) filter (where rn <= 200) - 1 as dist_200dma,
    stddev_samp(ret) filter (where rn <= 252) * sqrt(252) as vol_1y,
    avg(value) filter (where rn <= 63) / 1e7 as adv_3m_cr,
    count(*) as days
from r group by symbol, exchange
"""

DRAWDOWN_SQL = """
with a as ({adjusted}),
w as (select *, row_number() over (partition by symbol, exchange order by date desc) as rn
      from a where date <= $as_of),
d as (select symbol, exchange, adj_close / max(adj_close) over (partition by symbol, exchange order by date
             rows between unbounded preceding and current row) - 1 as dd
      from w where rn <= 252)
select symbol, exchange, min(dd) as max_dd_1y from d group by symbol, exchange
"""


def price_factors(db: duckdb.DuckDBPyConnection, as_of: date, lookback_days: int = 400) -> dict[str, dict]:
    """Price factors for every stock on `as_of`, keyed by symbol (NSE first, then BSE-only)."""
    since = date.fromordinal(as_of.toordinal() - lookback_days)
    adjusted = ADJUSTED_SQL.format(symbol_filter="")
    params = {"since": since, "as_of": as_of}
    cur = db.execute(FACTORS_SQL.format(adjusted=adjusted), params)
    cols = [c[0] for c in cur.description]
    out: dict[str, dict] = {}
    for row in sorted(cur.fetchall(), key=lambda r: r[1] != "NSE"):
        rec = dict(zip(cols, row))
        out.setdefault(rec["symbol"], rec)
    for symbol, exchange, dd in db.execute(DRAWDOWN_SQL.format(adjusted=adjusted), params).fetchall():
        if symbol in out and out[symbol]["exchange"] == exchange:
            out[symbol]["max_dd_1y"] = dd
    return out
