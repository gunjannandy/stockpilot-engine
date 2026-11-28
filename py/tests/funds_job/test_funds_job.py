import json
from datetime import date, timedelta

from stockpilot.jobs import funds as job

TODAY = date(2026, 11, 27)


def series(start: float, yearly: float, years: int = 6) -> list[tuple[str, float]]:
    out = []
    for i in range(years * 365):
        d = TODAY - timedelta(days=years * 365 - i)
        out.append((d.isoformat(), round(start * (1 + yearly) ** (i / 365), 4)))
    return out


def test_weekly_keeps_one_nav_a_week_over_five_years_and_skips_zeros():
    s = series(10, 0.1) + [(TODAY.isoformat(), 0.0)]
    w = job.weekly(s, TODAY)
    assert 255 <= len(w) <= 265
    assert w == sorted(w, key=lambda n: n["d"]) and all(n["v"] > 0 for n in w)
    assert w[0]["d"] >= str(TODAY - timedelta(days=365 * 5 + 7))


def test_stats_of_a_steady_ten_percent_fund_and_of_a_fund_that_fell():
    st = job.stats(job.weekly(series(10, 0.10), TODAY))
    assert st["r1"] == st["r3"] == st["r5"] or abs(st["r3"] - 10) < 0.3
    assert abs(st["r1"] - 10) < 0.5 and st["max_fall"] == 0 and st["roll_loss_share"] == 0
    dip = [{"d": f"2026-0{m}-01", "v": v} for m, v in ((1, 100), (2, 80), (3, 90))]
    assert job.max_fall(dip) == -20.0


def test_category_middle_needs_five_funds():
    rows = [{"category": "A", "r1": float(i), "r3": None, "r5": None} for i in range(5)]
    rows.append({"category": "B", "r1": 1.0, "r3": None, "r5": None})
    job.with_categories(rows)
    assert rows[0]["cat_r1"] == 2.0 and rows[0]["category_n"] == 5
    assert rows[-1]["cat_r1"] is None and rows[-1]["category_n"] == 1
    assert rows[0]["cat_r3"] is None


def test_choose_prefers_equity_then_size_and_caps():
    funds = [{"id": "d", "category": "Debt Scheme - Gilt", "aum_cr": 9999}, {"id": "e1", "category": "Equity Scheme - Large Cap", "aum_cr": 10},
             {"id": "e2", "category": "Equity Scheme - Large Cap", "aum_cr": 500}, {"id": "e3", "category": "Equity Scheme - Small", "aum_cr": None}]
    assert [f["id"] for f in job.choose(funds)] == ["e2", "e1", "e3", "d"]
    assert [f["id"] for f in job.choose(funds, 2)] == ["e2", "e1"]


NAVALL = """Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date
Open Ended Schemes(Equity Scheme - Flexi Cap Fund)
Alpha Mutual Fund
100001;-;-;Alpha Flexi Cap Fund - Direct Plan - Growth Option;50.0;27-Nov-2026
100002;-;-;Alpha Flexi Cap Fund - Regular Plan - Growth Option;45.0;27-Nov-2026
""".encode()


def test_collect_publishes_the_direct_growth_fund_with_stats_and_survives_a_costs_failure():
    nav = {"data": [{"date": d.split("-")[2] + "-" + d.split("-")[1] + "-" + d.split("-")[0], "nav": str(v)} for d, v in reversed(series(20, 0.12))]}

    def fetch(url):
        if "NAVAll" in url:
            return NAVALL
        if "mfapi.in/mf/100001" in url:
            return json.dumps(nav).encode()
        raise OSError("costs down")

    notes = []
    rows = job.collect(TODAY, fetch, sleep=lambda _: None, progress=notes.append)
    assert len(rows) == 1
    r = rows[0]
    assert r["code"] == 100001 and r["ter"] is None and r["amc"] == "Alpha Mutual Fund"
    assert abs(r["r1"] - 12) < 0.6 and len(json.loads(r["navs_json"])) > 200
    assert any("costs not read" in n for n in notes)
