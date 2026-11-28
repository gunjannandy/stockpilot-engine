"""C-034-1: similar-call grouping and counts from fixtures."""
from stockpilot.jobs.forecast.verdict import similar, verdict


def past(n, verdict_="Buy", chance=0.60, beats=0, horizon=63):
    return [{"made_on": f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}", "verdict": verdict_, "chance": chance, "horizon_days": horizon,
             "beat": i < beats} for i in range(n)]


def test_groups_same_verdict_horizon_and_nearby_chance():
    rows = past(10, beats=6) + past(5, "Hold", 0.45) + past(4, chance=0.80) + past(3, horizon=126)
    assert similar(rows, "Buy", 0.62, 63) == (10, 6)


def test_only_the_last_24_count_newest_first():
    rows = past(40)
    for i, r in enumerate(rows):
        r["beat"] = i >= 30              # the newest ten (the last indexes) all beat the Nifty
    n, beat = similar(rows, "Buy", 0.60, 63)
    assert n == 24 and beat == 10


def test_nothing_like_it_gives_zero_and_the_verdict_lines():
    assert similar([], "Buy", 0.6, 63) == (0, 0)
    assert [verdict(c) for c in (0.7, 0.54, 0.45, 0.35, 0.2, None)] == ["Buy", "Watch", "Hold", "Weak", "Sell", "No view yet"]
