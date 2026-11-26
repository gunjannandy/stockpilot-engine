import numpy as np

from stockpilot.mechanical import model


def test_logistic_learns_a_real_signal_and_ignores_noise():
    rng = np.random.default_rng(1)
    x = rng.normal(size=(4000, 3))
    y = (rng.random(4000) < 1 / (1 + np.exp(-1.5 * x[:, 0]))).astype(float)
    m = model.fit_logistic(x, y, l2=1.0)
    assert m.coef[0] > 1.0 and abs(m.coef[1]) < 0.2 and abs(m.coef[2]) < 0.2
    p = m.predict(x)
    assert p.min() > 0 and p.max() < 1


def test_logistic_regularisation_shrinks_weights():
    rng = np.random.default_rng(2)
    x = rng.normal(size=(200, 2))
    y = (x[:, 0] > 0).astype(float)
    assert abs(model.fit_logistic(x, y, l2=50).coef[0]) < abs(model.fit_logistic(x, y, l2=0.1).coef[0])


def test_thin_bucket_rate_is_pulled_to_the_parent_by_the_effective_sample():
    # 10 start rows, all hits, overlap 3 -> 3.3 effective: far from 100%
    rate = model.smoothed_rate(hits=10, n=10, parent=0.5, overlap=3.0, k=30)
    assert 0.5 < rate < 0.6
    big = model.smoothed_rate(hits=9000, n=10000, parent=0.5, overlap=3.0, k=30)
    assert big > 0.85


def test_blend_averages_in_log_odds_and_clips_to_15_85():
    assert abs(model.blend(np.array([0.5]), np.array([0.5]))[0] - 0.5) < 1e-9
    assert model.blend(np.array([0.99]), np.array([0.99]))[0] == 0.85
    assert model.blend(np.array([0.01]), np.array([0.01]))[0] == 0.15
    mid = model.blend(np.array([0.9]), np.array([0.5]))[0]
    assert 0.5 < mid < 0.85 and abs(mid - 1 / (1 + np.exp(-np.log(9) / 2))) < 1e-9


def test_platt_pulls_overconfident_scores_back_to_what_happened():
    rng = np.random.default_rng(3)
    true_p = rng.uniform(0.3, 0.7, 5000)
    y = (rng.random(5000) < true_p).astype(float)
    overconfident = np.clip(0.5 + (true_p - 0.5) * 3, 0.01, 0.99)
    cal = model.fit_platt(overconfident, y)
    fixed = cal.apply(overconfident)
    assert np.mean((fixed - y) ** 2) < np.mean((overconfident - y) ** 2)
    assert np.all(np.diff(cal.apply(np.linspace(0.3, 0.7, 20))) > 0)
