import numpy as np

from panel_fixture import make_panel
from stockpilot.mechanical import walkforward as wf


def test_features_never_include_the_information_only_signals():
    assert "delivery_info" not in wf.FEATURES and "reversal_1m_info" not in wf.FEATURES
    assert len(wf.FEATURES) <= 8


def test_dataset_outcomes_look_forward_exactly_h_days_and_start_days_are_a_month_apart():
    p = make_panel()
    ds = wf.build_dataset(p, h=63)
    assert len(np.unique(ds.t)) > 10
    assert set(np.diff(np.unique(ds.t))) == {wf.STEP}
    i = 5
    t, s = ds.t[i], ds.stock[i]
    stock_ret = p.close[t + 63, s] / p.close[t, s] - 1
    assert abs(ds.ret[i] - stock_ret) < 1e-12
    bench_ret = p.bench[t + 63] / p.bench[t] - 1
    assert ds.y[i] == float(stock_ret - bench_ret > wf.HURDLE)


def test_walk_forward_never_trains_on_outcomes_it_could_not_have_known():
    p = make_panel()
    rep = wf.walk_forward(p, h=63)
    for f in rep["folds"]:
        assert f["train_last_start"] + 63 + 63 <= f["test_first_start"]      # horizon plus a purge gap of the same size


def test_report_beats_both_baselines_on_a_market_where_momentum_is_real():
    rep = wf.walk_forward(make_panel(n=80, days=1500, seed=11), h=63)
    b = rep["brier"]
    assert set(b) >= {"final", "base_rate_alone", "always_50", "bucket", "logistic"}
    assert b["final"] < b["always_50"] and b["final"] < b["base_rate_alone"]
    assert rep["n_test"] > 500


def test_calibration_bins_hold_predicted_actual_and_count():
    rep = wf.walk_forward(make_panel(n=80, days=1500, seed=11), h=63)
    bins = rep["calibration"]
    assert sum(b["n"] for b in bins) == rep["n_test"]
    for b in bins:
        assert 0 <= b["predicted"] <= 1 and 0 <= b["actual"] <= 1 and b["n"] > 0
    # a calibrated model: the heavy bins sit near the diagonal
    heavy = [b for b in bins if b["n"] >= 0.2 * rep["n_test"]]
    assert heavy and all(abs(b["predicted"] - b["actual"]) < 0.1 for b in heavy)


def test_range_coverage_is_reported_and_close_to_the_80_percent_target():
    rep = wf.walk_forward(make_panel(n=80, days=1500, seed=11), h=63)
    c = rep["coverage"]
    assert c["target"] == 0.8 and c["n"] == rep["n_test"]
    assert 0.65 < c["observed"] < 0.92
    assert 0 < c["alpha_final"] < 1


def test_report_says_information_only_signals_are_not_in_the_model():
    rep = wf.walk_forward(make_panel(), h=63)
    assert rep["information_only"] == ["delivery_info", "reversal_1m_info"]
    assert set(rep["reversal_check"]) == {"low_third_hit_rate", "high_third_hit_rate"}
