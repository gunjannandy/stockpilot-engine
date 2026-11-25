"""Measuring how often a target a given share of the swing away is reached before the stop, on synthetic series."""
import json
import math
import random

import pytest

from stockpilot import levels, levels_calibration as cal


def walk(n=400, drift=0.0, vol=0.02, seed=1, start=100.0):
    rnd, c, out = random.Random(seed), start, []
    for _ in range(n):
        c *= math.exp(drift + vol * rnd.gauss(0, 1))
        out.append((c * (1 + abs(rnd.gauss(0, vol / 2))), c * (1 - abs(rnd.gauss(0, vol / 2))), c))
    return [r[0] for r in out], [r[1] for r in out], [r[2] for r in out]


def test_a_flat_series_never_reaches_a_target_and_one_always_does():
    highs = [101.0] * 300; lows = [99.0] * 300; closes = [100.0] * 300
    flat = cal.measure_series(highs, lows, closes, shares=(0.5, 1.0), step=20)
    assert flat and all(o["hit"][0.5] == 0 for o in flat)
    up = [100 * 1.01 ** i for i in range(300)]
    ramp = cal.measure_series([c * 1.005 for c in up], [c * 0.995 for c in up], up, shares=(0.5,), step=20)
    assert ramp and all(o["hit"][0.5] == 1 for o in ramp)


def test_the_stop_hit_first_counts_as_a_miss():
    n = 260
    closes = [100.0] * n; highs = [100.5] * n; lows = [99.5] * n
    for i in range(150, n):          # crash: the stop goes before any rise
        closes[i] = 80.0; highs[i] = 80.5; lows[i] = 79.5
    out = cal.measure_series(highs, lows, closes, shares=(0.5,), step=1)
    crash = [o for o in out if o["i"] == 140]
    assert crash and crash[0]["hit"][0.5] == 0 and crash[0]["stopped"] == 1


def test_hit_rate_falls_as_the_share_grows():
    h, l, c = walk(1500)
    out = cal.measure_series(h, l, c, shares=(0.2, 0.5, 1.0), step=5)
    r = lambda s: sum(o["hit"][s] for o in out) / len(out)
    assert len(out) > 100 and r(0.2) >= r(0.5) >= r(1.0)


def test_choose_share_lands_on_one_in_two():
    curve = {0.2: 0.8, 0.4: 0.6, 0.6: 0.4, 0.8: 0.2}
    assert cal.choose_share(curve, 0.5) == pytest.approx(0.5)
    assert cal.choose_share({0.2: 0.3, 0.4: 0.2}, 0.5) == 0.2      # never reaches one in two: the smallest share
    assert cal.choose_share({0.2: 0.9, 0.4: 0.8}, 0.5) == 0.4      # always above: the largest share tried


def test_buckets_by_volatility_and_size():
    assert cal.bucket(0.01, 500) != cal.bucket(0.04, 500)
    assert cal.bucket(0.02, 1) != cal.bucket(0.02, 500)
    assert cal.bucket(None, None) == cal.FALLBACK


def test_levels_read_the_calibration_and_export_the_hit_rate(tmp_path, monkeypatch):
    b = cal.bucket(0.02, 100)
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"v": 1, "default_share": 0.5, "buckets": {b: {"share": 0.3, "curve": {"0.2": 0.7, "0.4": 0.5}, "n": 900}}}))
    monkeypatch.setattr(cal, "PATH", f); cal.load.cache_clear()
    d = {"price": {"close": 100.0, "atr": 2.0, "atr_pct": 0.02, "liquidity_cr": 100, "support": [], "resistance": []}}
    lv = levels.for_stock(d)
    assert lv["target"] == pytest.approx(100 + 0.3 * 2 * 63 ** 0.5, abs=0.01)
    assert lv["target_hit_n"] == 900 and 0.5 < lv["target_hit_rate"] < 0.7
    f.write_text("{}"); cal.load.cache_clear()
    assert "target_hit_rate" not in levels.for_stock(d)        # no calibration: the old half-swing, no claim made
    cal.load.cache_clear()
