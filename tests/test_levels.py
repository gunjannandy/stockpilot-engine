"""Entry, stop and target from the price structure. The model may flag a level; it never sets one."""
import pytest

from stockpilot import levels, levels_calibration


@pytest.fixture(autouse=True)
def no_calibration(tmp_path, monkeypatch):
    """These tests pin the fallback rule (half a swing); the measured share is tested in test_levels_calibration."""
    monkeypatch.setattr(levels_calibration, "PATH", tmp_path / "none.json")
    levels_calibration.load.cache_clear()
    yield
    levels_calibration.load.cache_clear()


def d(close=100.0, atr=2.0, support=(96.0, 90.0), resistance=(104.0, 120.0)):
    return {"price": {"close": close, "atr": atr, "support": list(support), "resistance": list(resistance)}}


def test_stop_sits_half_a_daily_move_under_the_nearest_support():
    lv = levels.for_stock(d())
    assert lv["entry"] == 100.0
    assert lv["stop"] == pytest.approx(95.0)             # 96 - 0.5 * 2


def test_stop_is_never_more_than_three_daily_moves_below_entry():
    lv = levels.for_stock(d(support=(80.0,)))
    assert lv["stop"] == pytest.approx(94.0)             # 100 - 3 * 2, not 80 - 1


def test_stop_ignores_support_at_or_above_entry():
    lv = levels.for_stock(d(support=(101.0, 97.0)))
    assert lv["stop"] == pytest.approx(96.0)             # 97 - 1


def test_with_no_support_below_the_stop_is_two_daily_moves_down():
    lv = levels.for_stock(d(support=()))
    assert lv["stop"] == pytest.approx(96.0)


SWING = 2.0 * 63 ** 0.5               # a typical 3-month swing for a stock that moves 2 a day: about 15.9


def test_target_is_half_a_typical_three_month_swing_not_a_multiple_of_the_risk():
    lv = levels.for_stock(d(resistance=()))
    assert lv["target"] == pytest.approx(100 + 0.5 * SWING, abs=0.01)           # about 108, not 110: the stop no longer sets the target


def test_a_quiet_stock_aims_lower_and_a_wild_one_higher():
    quiet, wild = levels.for_stock(d(atr=1.0, resistance=())), levels.for_stock(d(atr=4.0, resistance=()))
    assert quiet["target"] < levels.for_stock(d(resistance=()))["target"] < wild["target"]


def test_a_recent_high_inside_the_swing_is_the_target():
    lv = levels.for_stock(d(resistance=(104.0, 120.0)))              # 104 is two daily moves up and under the swing target
    assert lv["target"] == pytest.approx(104.0)
    assert "recent high" in lv["why"]


def test_a_recent_high_less_than_one_daily_move_away_is_ignored():
    lv = levels.for_stock(d(resistance=(101.0,)))
    assert lv["target"] == pytest.approx(100 + 0.5 * SWING, abs=0.01)


def test_a_recent_high_beyond_the_swing_does_not_stretch_the_target():
    lv = levels.for_stock(d(resistance=(112.0, 130.0)))
    assert lv["target"] == pytest.approx(100 + 0.5 * SWING, abs=0.01)


def test_why_is_plain_english_with_rupee_prices():
    why = levels.for_stock(d())["why"]
    assert "₹95" in why and "₹104" in why and "stop-loss" not in why.lower()


def test_no_prices_means_no_levels():
    assert levels.for_stock({"price": {}}) is None
    assert levels.for_stock({}) is None
    assert levels.for_stock(d(atr=None)) is None


def test_the_shipped_calibration_is_read_and_exports_a_hit_rate():
    levels_calibration.load.cache_clear()
    from pathlib import Path
    levels_calibration.PATH = Path(levels_calibration.__file__).resolve().parents[2] / "config" / "levels_calibration.json"
    try:
        levels_calibration.load.cache_clear()
        lv = levels.for_stock(d(resistance=()))
        assert 0.4 <= lv["target_hit_rate"] <= 0.6 and lv["target_hit_n"] > 1000
    finally:
        levels_calibration.load.cache_clear()


def test_target_reason_states_the_share_actually_used(tmp_path, monkeypatch):
    """Audit F-M: the calibrated share is about 0.21, so the sentence must not say 'half a typical move'."""
    import json
    f = tmp_path / "cal.json"
    f.write_text(json.dumps({"buckets": {"all": {"share": 0.21, "curve": {"0.2": 0.5, "1.0": 0.15}, "n": 1000}}}))
    monkeypatch.setattr(levels_calibration, "PATH", f)
    levels_calibration.load.cache_clear()
    why = levels.for_stock(d(resistance=()))["why"]
    assert "half" not in why and "21%" in why
