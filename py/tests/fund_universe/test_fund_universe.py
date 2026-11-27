"""Fund universe: every AMFI scheme maps to exactly one fund; NAV history in windows of at most 90 days; TER and AUM
joined by name; coverage reported."""
import json
from datetime import date

from stockpilot.sources import fund_universe as fu, fundcosts

NAVALL = """Scheme Code;ISIN Div Payout/ ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date

Open Ended Schemes(Equity Scheme - Flexi Cap Fund)

Parag Parikh Mutual Fund

122639;INF879O01027;-;Parag Parikh Flexi Cap Fund - Direct Plan - Growth;95.4585;20-Nov-2026
122640;INF879O01035;-;Parag Parikh Flexi Cap Fund - Direct Plan - IDCW;90.1;20-Nov-2026
122641;INF879O01043;-;Parag Parikh Flexi Cap Fund - Regular Plan - Growth;88.2;20-Nov-2026
122642;-;-;Parag Parikh Flexi Cap Fund - Regular Plan - Monthly IDCW;N.A.;20-Nov-2026

Open Ended Schemes(Equity Scheme - Large Cap Fund)

Axis Mutual Fund

120503;INF846K01EW2;-;Axis Bluechip Fund - Direct Plan - Growth Option;60.0;20-Nov-2026
120504;INF846K01EX0;INF846K01EY8;Axis Bluechip Fund - Regular Plan - Growth Option;50.0;20-Nov-2026

Close Ended Schemes(Income)

Axis Mutual Fund

130001;INF846K01ZZ9;-;Axis Fixed Term Plan - Series 99 (1100 Days) - Direct Plan - Growth;10.5;20-Nov-2026
"""


def schemes():
    return fu.parse_navall(NAVALL.encode())


def test_every_scheme_is_parsed_even_with_no_nav():
    s = schemes()
    assert [x["code"] for x in s] == [122639, 122640, 122641, 122642, 120503, 120504, 130001]
    na = [x for x in s if x["code"] == 122642][0]
    assert na["nav"] is None and na["amc"] == "Parag Parikh Mutual Fund" and na["category"] == "Equity Scheme - Flexi Cap Fund"
    assert (na["plan"], na["option"]) == ("Regular", "IDCW")


def test_every_scheme_maps_to_one_fund_with_plan_and_option_variants():
    s = schemes()
    funds = fu.group_funds(s)
    assert len(funds) == 3
    assert sorted(c for f in funds for v in f["variants"] for c in [v["code"]]) == sorted(x["code"] for x in s)
    pp = next(f for f in funds if f["name"] == "Parag Parikh Flexi Cap Fund")
    assert pp["amc"] == "Parag Parikh Mutual Fund" and len(pp["variants"]) == 4
    assert {(v["plan"], v["option"]) for v in pp["variants"]} == {("Direct", "Growth"), ("Direct", "IDCW"), ("Regular", "Growth"), ("Regular", "IDCW")}
    assert pp["primary_code"] == 122639          # Direct Growth is the one we chart


def test_fund_ids_are_stable_and_unique():
    a, b = fu.group_funds(schemes()), fu.group_funds(list(reversed(schemes())))
    assert sorted(fu.fund_id(f) for f in a) == sorted(fu.fund_id(f) for f in b)
    assert len({fu.fund_id(f) for f in a}) == 3


def test_same_name_in_two_houses_stays_two_funds():
    s = [dict(code=1, amc="A Mutual Fund", category="Equity Scheme - Large Cap Fund", name="Bluechip Fund - Direct Plan - Growth", plan="Direct", option="Growth", label="Growth", nav=1.0, isin=None, day=None),
         dict(code=2, amc="B Mutual Fund", category="Equity Scheme - Large Cap Fund", name="Bluechip Fund - Direct Plan - Growth", plan="Direct", option="Growth", label="Growth", nav=1.0, isin=None, day=None)]
    assert len(fu.group_funds(s)) == 2


def test_windows_never_exceed_90_days_and_cover_the_range():
    w = fu.windows(date(2006, 4, 1), date(2026, 11, 20))
    assert w[0][0] == date(2006, 4, 1) and w[-1][1] == date(2026, 11, 20)
    assert all((b - a).days + 1 <= 90 for a, b in w)
    assert all(w[i][1] + (date(2006, 1, 2) - date(2006, 1, 1)) == w[i + 1][0] for i in range(len(w) - 1))


def test_history_rows_keep_only_wanted_codes():
    report = ("Scheme Code;Scheme Name;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Repurchase Price;Sale Price;Date\n"
              "122639;X;INF;-;95.1;;;19-Nov-2026\n999;Y;INF;-;5;;;19-Nov-2026\n122639;X;INF;-;N.A.;;;18-Nov-2026\nbad line\n")
    rows = list(fu.parse_history(report.splitlines(), {122639}))
    assert rows == [(122639, date(2026, 11, 19), 95.1)]


def test_nav_run_loads_windows_resumes_and_shrinks_refused_windows():
    calls = []

    def fetch(start, end):
        calls.append((start, end))
        if (end - start).days + 1 > 40:
            return None                      # AMFI refuses long windows: the loader halves and tries again
        return f"1;N;I;-;{10 + len(calls)};;;{start.strftime('%d-%b-%Y')}\n".encode()

    state = {"done": []}
    got = fu.load_nav_history({1}, date(2026, 1, 1), date(2026, 3, 31), fetch, state, pause=0)
    assert [(b - a).days + 1 for a, b in calls[:3]] == [90, 45, 23] and got["rows"] >= 2
    assert state["done"][0][0] == "2026-01-01" and state["done"][-1][1] == "2026-03-31"
    n = len(calls)
    fu.load_nav_history({1}, date(2026, 1, 1), date(2026, 3, 31), fetch, state, pause=0)
    assert len(calls) == n                   # nothing new to fetch


def test_costs_join_by_name_and_coverage_is_reported():
    funds = fu.group_funds(schemes())
    k = fundcosts.scheme_key
    ter = {k("Parag Parikh Flexi Cap Fund"): (1.5, 0.6)}
    aum = {k("Parag Parikh Flexi Cap Fund"): 90000.0, k("Axis Bluechip Fund"): 30000.0}
    fu.attach_costs(funds, ter, aum)
    pp = next(f for f in funds if f["amc"].startswith("Parag"))
    assert (pp["ter_regular"], pp["ter_direct"], pp["aum_cr"]) == (1.5, 0.6, 90000.0)
    ax = next(f for f in funds if f["name"] == "Axis Bluechip Fund")
    assert ax["ter_direct"] is None and ax["aum_cr"] == 30000.0
    cov = fu.coverage(funds, {122639: 4000}, schemes_total=7)
    assert cov["funds"] == 3 and cov["schemes"] == 7 and cov["schemes_mapped"] == 7
    assert cov["ter_pct"] == 33.3 and cov["aum_pct"] == 66.7
    assert cov["nav_history"]["funds_with_history"] == 1


def test_published_files_match_the_contract(tmp_path):
    funds = fu.group_funds(schemes())
    fu.attach_costs(funds, {}, {})
    nav = {122639: [(date(2026, 11, 18), 94.0), (date(2026, 11, 19), 95.1)]}
    cov = fu.publish(funds, nav, tmp_path, built_at="2026-11-25T09:15:00+05:30", schemes_total=7)
    idx = json.loads((tmp_path / "funds/index.json").read_text())
    assert len(idx["entries"]) == 3 and idx["counts"]["schemes"] == 7
    e = next(x for x in idx["entries"] if x["name"] == "Parag Parikh Flexi Cap Fund")
    assert "parag parikh" in " ".join(e["aliases"])
    facts = json.loads((tmp_path / f"funds/{e['id']}.json").read_text())
    assert facts["nav"]["dates"] == ["2026-11-18", "2026-11-19"] and facts["nav"]["nav"] == [94.0, 95.1]
    assert len(facts["variants"]) == 4 and cov["nav_history"]["funds_with_history"] == 1




def test_the_eight_column_navall_layout_groups_too():
    from pathlib import Path
    s = fu.parse_navall((Path(__file__).parents[1] / "fixtures" / "NAVAll.txt").read_bytes())
    funds = fu.group_funds(s)
    assert s and sum(len(f["variants"]) for f in funds) == len(s)
    kids = next(f for f in funds if f["name"] == "Axis Children's Fund")
    assert {(v["plan"], v["option"]) for v in kids["variants"]} == {("Direct", "Growth"), ("Direct", "IDCW")}
