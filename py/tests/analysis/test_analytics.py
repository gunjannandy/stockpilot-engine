from datetime import date, timedelta

from pytest import approx

from stockpilot import store

from stockpilot.analysis import analytics


def add(db, symbol, day, close, prev_close, value=2e7):
    db.execute("insert into prices values (?, ?, 'NSE', 'EQ', ?, ?, ?, ?, ?, 1000, ?, 10)",
               [day, symbol, close, close, close, close, prev_close, value])


def test_a_split_is_adjusted_out_of_history_but_small_moves_are_not(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    d = date(2026, 1, 5)
    add(db, "X", d, 1000, 990)
    add(db, "X", d + timedelta(1), 990, 1000)            # an ordinary 1% fall
    add(db, "X", d + timedelta(2), 510, 495)             # 2:1 split; the action table, not prev_close, drives the adjustment
    add(db, "X", d + timedelta(3), 520, 510)
    db.execute("insert into corporate_actions (symbol, ex_date, kind, numerator, denominator) "
               "values ('X', ?, 'split', 2, 1)", [d + timedelta(2)])
    adj = dict(analytics.adjusted_closes(db, "X", since=d))
    assert adj[d] == approx(500)
    assert adj[d + timedelta(1)] == approx(495)
    assert adj[d + timedelta(2)] == approx(510)
    assert adj[d + timedelta(3)] == approx(520)


def test_price_factors_on_a_steady_riser(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    start = date(2025, 1, 1)
    closes = [100 * 1.001 ** i for i in range(300)]
    for i, c in enumerate(closes):
        add(db, "UP", start + timedelta(i), c, closes[i - 1] if i else c, value=3e7)
    f = analytics.price_factors(db, as_of=start + timedelta(299))["UP"]
    assert f["ret_12m"] == approx(1.001 ** 252 - 1, rel=1e-6)
    assert f["ret_6m"] == approx(1.001 ** 126 - 1, rel=1e-6)
    sma200 = sum(closes[100:]) / 200
    assert f["dist_200dma"] == approx(closes[-1] / sma200 - 1, rel=1e-6)
    assert f["max_dd_1y"] == approx(0, abs=1e-9)
    assert f["adv_3m_cr"] == approx(3.0)            # ₹3 crore a day
    assert f["vol_1y"] == approx(0, abs=1e-6)
