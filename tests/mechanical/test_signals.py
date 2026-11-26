import numpy as np

from panel_fixture import make_panel
from stockpilot.mechanical import signals


def test_signals_are_between_zero_and_one_and_named_as_the_contract():
    p = make_panel()
    s = signals.compute(p, p.n_days - 1)
    assert set(s) == set(signals.NAMES)
    for name in ("momentum", "near_52w_high", "low_volatility", "trend", "market_regime", "liquidity"):
        v = s[name][~np.isnan(s[name])]
        assert len(v) == p.n_stocks and v.min() >= 0 and v.max() <= 1


def test_momentum_rank_puts_the_best_six_minus_one_month_return_on_top():
    p = make_panel()
    t = p.n_days - 1
    s = signals.compute(p, t)
    six_one = p.close[t - 21] / p.close[t - 126] - 1
    assert np.argmax(s["momentum"]) == np.argmax(six_one)
    assert np.argmin(s["momentum"]) == np.argmin(six_one)


def test_near_high_is_one_at_a_fresh_high_and_reversal_is_plain_month_return():
    p = make_panel()
    p.close[-1, 0] = p.close[:, 0].max() * 1.1
    s = signals.compute(p, p.n_days - 1)
    assert s["near_52w_high"][0] == 1.0
    assert abs(s["reversal_1m_info"][3] - (p.close[-1, 3] / p.close[-22, 3] - 1)) < 1e-12


def test_a_stock_with_too_little_history_gets_nan_not_a_guess():
    p = make_panel()
    p.close[:1000, 5] = np.nan
    s = signals.compute(p, p.n_days - 1)
    assert np.isnan(s["momentum"][5]) and not np.isnan(s["momentum"][6])


def test_delivery_and_fundamentals_pass_through_only_as_given():
    p = make_panel()
    s = signals.compute(p, p.n_days - 1, extras={"NSE:S001": {"delivery_info": 0.4, "quality": 0.7}})
    assert s["delivery_info"][1] == 0.4 and s["quality"][1] == 0.7
    assert np.isnan(s["delivery_info"][2]) and np.isnan(s["sector_value"][1])
