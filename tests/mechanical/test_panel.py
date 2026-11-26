from datetime import date, timedelta

import duckdb
import numpy as np

from stockpilot.mechanical import panel as pn
from stockpilot.sources import history


def _write(tmp_path, rows):
    con = duckdb.connect()
    con.execute(f"create table t ({history.DDL})")
    con.executemany(f"insert into t values ({', '.join('?' * len(history.NAMES))})", rows)
    con.execute(f"copy t to '{tmp_path}/prices-NSE-2026.parquet' (format parquet)")


def _row(sym, day, close, prev, value=1e6):
    return ("NSE", sym, None, "EQ", None, day, close, close, close, close, prev, 10, 1, value, "test")


def test_adjusted_close_follows_the_exchange_prev_close_across_a_split(tmp_path):
    d0 = date(2026, 1, 5)
    rows, price = [], 100.0
    for i in range(10):
        day = d0 + timedelta(days=i)
        if i == 5:      # a 2-for-1 split: price halves, the exchange's prev_close is already halved
            rows.append(_row("AAA", day, 51.0, 50.0))
            price = 51.0
        else:
            nxt = price * 1.01 if i else 100.0
            rows.append(_row("AAA", day, nxt, price if i else None))
            price = nxt
    _write(tmp_path, rows)
    p = pn.from_history(history.open_history(tmp_path), years=5)
    assert p.keys == [("NSE", "AAA")]
    steps = p.close[1:, 0] / p.close[:-1, 0] - 1
    assert np.all(np.abs(steps) < 0.05)       # no 50% crash in the adjusted series
    assert p.n_days == 10 and not np.isnan(p.close).any()


def test_market_proxy_is_the_median_move_of_liquid_stocks(tmp_path):
    d0 = date(2026, 1, 5)
    rows = []
    for sym, growth in (("AAA", 1.01), ("BBB", 1.02), ("CCC", 0.99)):
        price = 100.0
        for i in range(5):
            prev = price
            price = price * growth if i else 100.0
            rows.append(_row(sym, d0 + timedelta(days=i), price, prev if i else None))
    _write(tmp_path, rows)
    p = pn.from_history(history.open_history(tmp_path), years=5)
    assert abs(p.bench[1] / p.bench[0] - 1.01) < 1e-9
