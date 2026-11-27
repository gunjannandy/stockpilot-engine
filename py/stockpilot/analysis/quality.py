"""Data-quality report on the price history: missing trading days, stale symbols, unexplained jumps."""
from datetime import date, timedelta
from pathlib import Path

import duckdb

from stockpilot.analysis import analytics


def missing_days(db: duckdb.DuckDBPyConnection) -> list[date]:
    """Weekdays between the first and last price date with no prices and no NSE holiday."""
    first, last = db.execute("select min(date), max(date) from prices").fetchone()
    if first is None:
        return []
    have = {r[0] for r in db.execute("select distinct date from prices").fetchall()}
    holidays = {r[0] for r in db.execute("select date from holidays").fetchall()}
    out, d = [], first
    while d <= last:
        if d.weekday() < 5 and d not in have and d not in holidays:
            out.append(d)
        d += timedelta(days=1)
    return out


def stale_symbols(db: duckdb.DuckDBPyConnection, trading_days: int = 5) -> list[tuple[str, date]]:
    """Listed symbols whose last row is at least `trading_days` price dates before the latest date."""
    return db.execute("""
        with d as (select date, row_number() over (order by date desc) as n from (select distinct date from prices)),
        last as (select symbol, max(date) as last_date from prices group by symbol)
        select l.symbol, l.last_date from last l join d on d.date = l.last_date
        where d.n > ? and l.symbol in (select symbol from stocks) order by l.symbol""", [trading_days]).fetchall()


def within_trading_days(db: duckdb.DuckDBPyConnection, symbol: str, first: date, second: date, n: int) -> bool:
    """True when `first` and `second` are at most `n` of this symbol's price days apart."""
    lo, hi = sorted((first, second))
    between = db.execute("select count(distinct date) from prices where symbol = ? and date > ? and date <= ?",
                         [symbol, lo, hi]).fetchone()[0]
    return between <= n


EXPLAINED_WITHIN = 2      # trading days between a jump and an action that explains it

_MOVES_SQL = """
with a as ({prices}),
m as (select symbol, exchange, date, row_number() over (partition by symbol, exchange order by date) as rn,
             adj_close / lag(adj_close) over (partition by symbol, exchange order by date) - 1 as move from a),
c as (select m.symbol, m.exchange, min(m.rn) as rn, any_value(act.source) as source
      from (select symbol, ex_date, min(source) as source from corporate_actions group by symbol, ex_date) act
      join m on m.symbol = act.symbol and m.date >= act.ex_date
      group by m.symbol, m.exchange, act.ex_date)
select m.symbol, m.date, m.move, (select min(c.source) from c where c.symbol = m.symbol and c.exchange = m.exchange
                                  and abs(c.rn - m.rn) <= {within}) as source
from m where abs(m.move) > $t order by m.date, m.symbol
"""


def _jumps(db, prices_sql: str, threshold: float, since: date):
    return db.execute(_MOVES_SQL.format(prices=prices_sql, within=EXPLAINED_WITHIN),
                      {"since": since, "t": threshold}).fetchall()


def big_moves(db: duckdb.DuckDBPyConnection, threshold: float = 0.4, since: date = date(2015, 1, 1)):
    """(symbol, date, move): the adjusted close moved more than `threshold` and no corporate action falls
    within two trading days of it."""
    return [(s, d, m) for s, d, m, src in _jumps(db, analytics.ADJUSTED_SQL.format(symbol_filter=""), threshold, since)
            if src is None]


def explained_jump_counts(db: duckdb.DuckDBPyConnection, threshold: float = 0.4,
                          since: date = date(2015, 1, 1)) -> dict[str, int]:
    """Jumps in the raw (unadjusted) closes that a corporate action explains, counted by where the action came from."""
    raw = "select symbol, exchange, date, close as adj_close from prices where date >= $since"
    counts: dict[str, int] = {}
    for _, _, _, src in _jumps(db, raw, threshold, since):
        if src is not None:
            counts[src] = counts.get(src, 0) + 1
    return counts


def write_report(db: duckdb.DuckDBPyConnection, path: Path) -> Path:
    gaps, stale, moves = missing_days(db), stale_symbols(db), big_moves(db)
    lines = ["# Data quality", "", f"## Missing trading days ({len(gaps)})", ""]
    lines += [f"- {d}" for d in gaps] or ["None."]
    lines += ["", f"## Stale symbols, still listed ({len(stale)})", ""]
    lines += [f"- {s}: last row {d}" for s, d in stale] or ["None."]
    lines += ["", f"## Moves over 40% with no corporate action ({len(moves)})", ""]
    lines += [f"- {s} {d}: {m:+.0%}" for s, d, m in moves] or ["None."]
    explained = explained_jump_counts(db)
    lines += ["", f"## Moves over 40% a corporate action explains ({sum(explained.values())})", ""]
    lines += [f"- {src}: {n}" for src, n in sorted(explained.items())] or ["None."]
    path = Path(path)
    path.write_text("\n".join(lines) + "\n")
    return path
