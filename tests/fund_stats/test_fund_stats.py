"""T26: fund stats: yearly returns per fund, and the middle fund of each category month by month, so the page can say
how a fund did against its kind without loading every fund file."""
from datetime import date, timedelta

from stockpilot.sources import fund_stats as fs


def series(start, days, rate):
    d0 = date.fromisoformat(start)
    return [((d0 + timedelta(d)).isoformat(), 10 * (1 + rate) ** (d / 365)) for d in range(days)]


def test_month_ends_keep_the_last_nav_of_each_month():
    ends = fs.month_ends([("2024-01-30", 1.0), ("2024-01-31", 2.0), ("2024-02-01", 3.0), ("2024-02-29", 4.0)])
    assert ends == [("2024-01", 2.0), ("2024-02", 4.0)]


def test_yearly_return_over_a_window_or_none_when_too_young():
    ends = fs.month_ends(series("2015-01-01", 365 * 8, 0.12))
    assert abs(fs.yearly(ends, 3) - 12.0) < 0.5
    assert fs.yearly(fs.month_ends(series("2024-01-01", 200, 0.12)), 1) is None


ENTRIES = [{"id": f"f{i}", "category": "Equity Scheme - Flexi Cap Fund", "primary_code": i} for i in range(1, 7)] + \
          [{"id": "lone", "category": "Equity Scheme - Sectoral", "primary_code": 99}, {"id": "nocat", "category": None, "primary_code": 98}]


def nav():
    out = {i: series("2015-01-01", 365 * 8, 0.06 + 0.02 * i) for i in range(1, 7)}
    out[99] = series("2015-01-01", 365 * 8, 0.1)
    out[98] = series("2015-01-01", 365 * 8, 0.1)
    return out


def test_category_median_line_and_fund_returns():
    s = fs.build(ENTRIES, nav(), "2026-01-01T00:00:00+05:30")
    cat = next(c for c in s["categories"] if c["name"] == "Equity Scheme - Flexi Cap Fund")
    row = lambda i, k: s["funds"][k][s["funds"]["id"].index(i)]
    assert cat["n"] == 6 and len(cat["months"]) == len(cat["med1y"]) > 60
    assert 12 < cat["r3"] < 14                         # median of 8,10,12,14,16,18 is 13
    assert row("f1", "r3") < row("f6", "r3")
    assert row("f1", "r5") is not None


def test_thin_categories_get_no_median_line_and_uncategorised_funds_still_get_returns():
    s = fs.build(ENTRIES, nav(), "t")
    assert "Equity Scheme - Sectoral" not in [c["name"] for c in s["categories"]]      # one fund is not a category
    assert s["funds"]["r1"][s["funds"]["id"].index("nocat")] is not None
    assert "lone" in s["funds"]["id"]


def test_funds_with_no_history_are_left_out():
    s = fs.build(ENTRIES + [{"id": "empty", "category": None, "primary_code": 5}], {**nav(), 5: []}, "t")
    assert "empty" not in s["funds"]["id"]
