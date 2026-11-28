"""C-170-1 (screen half): the screen is deterministic, and the run's counts are the real analysed and passed."""
import random

from stockpilot.jobs.screen import build_file, rank, summary


def stocks():
    rng = random.Random(7)
    out = []
    for i in range(40):
        out.append({"symbol": f"S{i:02d}", "exchange": "NSE", "industry": "A" if i % 2 else "B",
                    **{f: rng.random() for f in ("quality", "value", "momentum", "risk")}})
    out.append({"symbol": "LONE", "exchange": "NSE", "industry": "C", "quality": 0.5, "value": 0.5, "momentum": 0.5, "risk": 0.5})
    out.append({"symbol": "THIN", "exchange": "NSE", "industry": "A", "quality": 0.5, "value": None, "momentum": None, "risk": None})
    return out


def test_same_rows_in_any_order_give_the_same_file_byte_for_byte():
    a = build_file(rank(stocks()), "2026-11-28")
    shuffled = stocks()
    random.Random(1).shuffle(shuffled)
    assert build_file(rank(shuffled), "2026-11-28") == a


def test_ranks_are_percentiles_in_industry_and_exclusions_say_why():
    rows = {r["symbol"]: r for r in rank(stocks())}
    assert rows["LONE"]["excluded"] == "too few peers in its industry" and rows["LONE"]["rank"] is None
    assert rows["THIN"]["excluded"] == "too few figures"
    ranks = sorted(r["rank"] for r in rows.values() if r["rank"])
    assert ranks == list(range(1, len(ranks) + 1))
    assert all(0 <= r["quality"] <= 1 for r in rows.values() if r["quality"] is not None)


def test_summary_counts_analysed_and_passed():
    s = summary(rank(stocks()))
    assert s == {"analysed": 42, "passed": 40}
