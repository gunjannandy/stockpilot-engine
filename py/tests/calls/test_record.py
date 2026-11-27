"""The record: scoring the model and the base rate side by side, one summary for status.json and the Record tab, and
the calibration that maps a model probability through the scored history."""
from datetime import date, timedelta

import pytest

from helpers import insert_prices
from stockpilot import store
from stockpilot.calls import record

D0 = date(2026, 1, 2)
D3 = D0 + timedelta(days=91)


def _market(db, moves):
    """A flat Nifty over the 3 months and one stock per entry in `moves` {symbol: end price from 100}."""
    for d, c in ((D0, 100.0), (D3, 100.0)):
        db.execute("insert into index_levels (date, name, close) values (?, 'Nifty 50', ?)", [d, c])
    for symbol, end in moves.items():
        insert_prices(db, [(D0, symbol, "NSE", "EQ", 100.0, 100.0, 100.0, 100.0, 100.0, 1000, 1e8, 10),
                           (D3, symbol, "NSE", "EQ", end, end, end, end, 100.0, 1000, 1e8, 10)])


def _call(db, symbol, p, base=None, base_n=None, hurdle=None, raw=None, made_on=D0):
    db.execute("insert into calls (made_on, symbol, kind, action, probability, raw_probability, base_rate, base_rate_n, hurdle, "
               "horizon_days) values (?, ?, 'candidate', 'buy', ?, ?, ?, ?, ?, 91)",
               [made_on, symbol, p, raw if raw is not None else p, base, base_n, hurdle])


def test_a_call_is_scored_against_the_nifty_and_the_hurdle(db):
    _market(db, {"WIN": 110.0, "NEAR": 101.0})           # +10% and +1% against a flat Nifty
    _call(db, "WIN", 0.7, hurdle=0.015)
    _call(db, "NEAR", 0.7, hurdle=0.015)                  # ahead of the Nifty, short of the hurdle
    assert record.score(db, D3 + timedelta(days=7)) == 2
    assert dict(db.execute("select symbol, score_3m from calls").fetchall()) == {"WIN": 1.0, "NEAR": 0.0}


def test_a_call_with_no_hurdle_is_scored_on_the_raw_beat_as_before(db):
    _market(db, {"NEAR": 101.0})
    _call(db, "NEAR", 0.7)
    record.score(db, D3 + timedelta(days=7))
    assert db.execute("select score_3m from calls").fetchone()[0] == 1.0


def test_summary_gives_hit_rate_and_brier_for_the_model_and_for_the_base_rate_alone(db):
    _market(db, {"WIN": 110.0, "LOSE": 95.0})
    _call(db, "WIN", 0.7, base=0.5, base_n=300)
    _call(db, "LOSE", 0.8, base=0.4, base_n=300)
    record.score(db, D3 + timedelta(days=7))
    s = record.summary(db)["3m"]
    assert s["n"] == 2 and s["hit_rate"] == 0.5
    assert s["brier"] == pytest.approx(((0.7 - 1) ** 2 + (0.8 - 0) ** 2) / 2)
    assert s["base_brier"] == pytest.approx(((0.5 - 1) ** 2 + (0.4 - 0) ** 2) / 2)


def test_the_base_rate_is_judged_only_where_it_had_a_sample(db):
    _market(db, {"WIN": 110.0, "LOSE": 95.0})
    _call(db, "WIN", 0.7, base=0.5, base_n=0)             # no sample: the 50% placeholder is not a forecast
    _call(db, "LOSE", 0.2, base=0.3, base_n=200)
    record.score(db, D3 + timedelta(days=7))
    s = record.summary(db)["3m"]
    assert s["base_brier"] == pytest.approx((0.3 - 0) ** 2)
    assert s["brier"] == pytest.approx(((0.7 - 1) ** 2 + 0.2 ** 2) / 2)     # the model is judged on every scored call


def test_the_model_is_judged_on_its_raw_probability_not_the_calibrated_one(db):
    _market(db, {"WIN": 110.0})
    _call(db, "WIN", 0.9, raw=0.6, base=0.5, base_n=100)  # decided on 0.9, the model said 0.6
    record.score(db, D3 + timedelta(days=7))
    assert record.summary(db)["3m"]["brier"] == pytest.approx((0.6 - 1) ** 2)


def test_the_latest_call_per_day_and_stock_counts_once(db):
    _market(db, {"WIN": 110.0})
    _call(db, "WIN", 0.1)
    _call(db, "WIN", 0.9)
    record.score(db, D3 + timedelta(days=7))
    assert record.summary(db)["3m"]["n"] == 1
    assert record.summary(db)["3m"]["brier"] == pytest.approx(0.01)


def test_model_added_value_waits_for_thirty_scored_calls(db):
    assert record.summary(db)["model_added_value"] is None
    _fill(db, 29, model_good=True)
    assert record.summary(db)["model_added_value"] is None and record.summary(db)["unproven"] is True
    _fill(db, 1, model_good=True, start=29)
    s = record.summary(db)
    assert s["scored_3m"] == 30 and s["unproven"] is False and s["model_added_value"] is True


def test_model_added_value_is_no_when_the_base_rate_alone_does_better(db):
    _fill(db, 30, model_good=False)
    assert record.summary(db)["model_added_value"] is False


def _fill(db, n, model_good, start=0, raw=None):
    """`n` scored 3-month calls on different days: half were hits. A good model says 0.8 on hits and 0.2 on misses."""
    for i in range(start, start + n):
        hit = i % 2 == 0
        p = (0.8 if hit else 0.2) if model_good else (0.2 if hit else 0.8)
        db.execute("insert into calls (made_on, symbol, kind, action, probability, raw_probability, base_rate, base_rate_n, "
                   "score_3m, horizon_days) values (?, 'AAA', 'candidate', 'buy', ?, ?, 0.5, 200, ?, 91)",
                   [D0 + timedelta(days=i), p, p if raw is None else raw[i], 1.0 if hit else 0.0])


def test_calibration_is_the_identity_below_thirty_scored_calls(db):
    _fill(db, 29, model_good=False)
    assert [record.calibrate(db, p) for p in (0.1, 0.5, 0.9)] == [0.1, 0.5, 0.9]


def test_calibration_is_monotonic_and_fixes_an_overconfident_model(db):
    raw = [0.55 + 0.4 * ((i * 7) % 20) / 19 for i in range(60)]          # the model says 0.55 to 0.95, whatever happens
    _fill(db, 60, model_good=True, raw=raw)
    grid = [i / 100 for i in range(0, 101, 5)]
    out = [record.calibrate(db, p) for p in grid]
    assert all(a <= b + 1e-12 for a, b in zip(out, out[1:]))             # never decreases as the model's chance rises
    assert all(0.0 <= v <= 1.0 for v in out)
    assert out != grid                                                    # it has learned something from the history
    assert record.calibrate(db, 0.9) < 0.9                                # said 90%, hit about half the time


def test_the_calibrator_can_be_fitted_once_and_applied_many_times(db):
    _fill(db, 40, model_good=True)
    cal = record.calibrator(db)
    assert cal(0.8) == record.calibrate(db, 0.8) and cal(0.2) == record.calibrate(db, 0.2)




def test_the_monthly_job_stores_the_buckets_and_one_run_row(tmp_path):
    from test_backtest import random_market
    from stockpilot.analysis import backtest
    db = store.open(tmp_path / "sp.duckdb")
    dates = random_market(db, 30, 700, seed=5, large={f"S{s:03d}" for s in range(0, 30, 2)})
    out = backtest.monthly(db, dates[-1] + timedelta(days=100), start=dates[250])
    assert out["buckets"] > 0 and out["samples"] > 0
    assert db.execute("select count(*) from base_rate_buckets").fetchone()[0] == out["buckets"]
    assert db.execute("select status from runs where job = 'base_rates'").fetchone()[0] == "ok"
    assert db.execute("select max(date) from prices").fetchone()[0] >= dates[-1]




# ---- R16: does learning from set-asides help? ---------------------------------------------------------------

def _learn_call(db, symbol, made_on, shown, score, reason="learned: Fewer banks", column="score_3m"):
    db.execute(f"insert into calls (made_on, symbol, kind, action, section, probability, horizon_days, change_reason, {column}) "
               "values (?, ?, 'candidate', 'buy', ?, 0.6, 91, ?, ?)",
               [made_on, symbol, "buy" if shown else "follow", None if shown else reason, score])


def _seed_learning(db, hid, shown):
    """hid and shown are lists of 3-month scores (1.0 beat the Nifty, 0.0 did not)."""
    for i, s in enumerate(hid):
        _learn_call(db, f"H{i}", D0, False, s)
    for i, s in enumerate(shown):
        _learn_call(db, f"S{i}", D0, True, s)


def test_learning_says_too_early_below_the_minimum_in_either_group(db):
    _seed_learning(db, [1.0] * (record.LEARNING_MIN_N - 1), [0.0] * 40)
    got = record.learning(db)["3m"]
    assert got["verdict"] == "too early" and got["hidden_n"] == record.LEARNING_MIN_N - 1 and got["shown_n"] == 40
    assert "too early" in got["line"]


def test_learning_says_better_by_points_when_the_hidden_buys_did_better(db):
    n = record.LEARNING_MIN_N
    _seed_learning(db, [1.0] * n, [1.0] * (n // 2) + [0.0] * (n - n // 2))     # 100% against 50%
    got = record.learning(db)["3m"]
    assert got["verdict"] == "better" and got["gap_points"] == pytest.approx(50.0)
    line = got["line"]
    assert "did better by 50 points" in line and f"n={n} and {n}" in line
    assert line.startswith("Stocks we hid because of what you set aside")


def test_learning_says_worse_and_same(db):
    n = record.LEARNING_MIN_N
    _seed_learning(db, [0.0] * n, [1.0] * n)
    assert record.learning(db)["3m"]["verdict"] == "worse"
    assert "did worse by 100 points" in record.learning(db)["3m"]["line"]
    db2_hid = [1.0, 0.0] * (n // 2)
    db.execute("delete from calls")
    _seed_learning(db, db2_hid, db2_hid)
    assert record.learning(db)["3m"]["verdict"] == "same"


def test_learning_ignores_adds_sells_and_unscored_calls_and_counts_a_rerun_once(db):
    n = record.LEARNING_MIN_N
    _seed_learning(db, [1.0] * n, [0.0] * n)
    db.execute("insert into calls (made_on, symbol, kind, action, section, probability, horizon_days, score_3m) "
               "values (?, 'ADD', 'candidate', 'add', 'buy', 0.6, 91, 1.0)", [D0])
    db.execute("insert into calls (made_on, symbol, kind, action, section, probability, horizon_days) "
               "values (?, 'NEW', 'candidate', 'buy', 'buy', 0.6, 91)", [D0])              # not scored yet
    db.execute("insert into calls (made_on, symbol, kind, action, section, probability, horizon_days, score_3m) "
               "values (?, 'S0', 'candidate', 'buy', 'buy', 0.6, 91, 0.0)", [D0])          # rerun of a shown call
    got = record.learning(db)["3m"]
    assert (got["hidden_n"], got["shown_n"]) == (n, n)


def test_learning_reads_each_window_and_other_demotions_do_not_count(db):
    n = record.LEARNING_MIN_N
    for i in range(n):
        _learn_call(db, f"H{i}", D0, False, 1.0, column="score_1m")
        _learn_call(db, f"S{i}", D0, True, 0.0, column="score_1m")
    db.execute("insert into calls (made_on, symbol, kind, action, section, probability, horizon_days, change_reason, score_1m) "
               "values (?, 'OTHER', 'candidate', 'buy', 'follow', 0.6, 91, 'blocked: budget', 1.0)", [D0])
    got = record.learning(db)
    assert got["1m"]["hidden_n"] == n and got["1m"]["verdict"] == "better"
    assert got["3m"]["hidden_n"] == 0 and got["3m"]["verdict"] == "too early"


