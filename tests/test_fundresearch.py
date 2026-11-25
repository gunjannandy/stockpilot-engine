"""Fund research: every researched fund gets a rank in its group, a plain verdict and a sentence, from NAVs and costs only."""
from datetime import date, timedelta

import pytest

from stockpilot import fundresearch, store

AS_OF = date(2026, 11, 20)
CAT = "Equity Scheme - Flexi Cap Fund"


@pytest.fixture
def db(tmp_path):
    d = store.open(tmp_path / "t.duckdb", job="test")
    yield d
    store.close(d)


def add_fund(db, code, weekly_growth, years=4.5, category=CAT, name=None, plan="Direct Plan", option="Growth", wobble=0.0):
    db.execute("insert into funds values (?, ?, null, ?, ?, ?, ?, 'House')", [code, f"INF{code:03d}", name or f"Fund {code}", plan, option, category])
    n, nav, day = int(years * 52), 10.0, AS_OF - timedelta(weeks=int(years * 52))
    for i in range(n + 1):
        db.execute("insert into navs values (?, ?, ?)", [day + timedelta(weeks=i), code, nav])
        nav *= 1 + weekly_growth + (wobble if i % 2 else -wobble)


def six(db):
    for code, g in enumerate((0.0030, 0.0025, 0.0020, 0.0015, 0.0010, 0.0005), start=1):
        add_fund(db, code, g)


def test_funds_are_ranked_by_three_year_return_inside_their_group(db):
    six(db)
    out = fundresearch.research(db, AS_OF)
    flexi = next(g for g in out["groups"] if g["name"] == "Flexi cap")
    assert [f["code"] for f in flexi["funds"]] == [1, 2, 3, 4, 5, 6]
    assert flexi["funds"][0]["rank"] == [1, 6] and flexi["funds"][5]["rank"] == [6, 6]
    assert flexi["funds"][0]["ret_3y"] > flexi["median_3y"] > flexi["funds"][5]["ret_3y"]


def test_the_top_fund_is_worth_considering_the_bottom_one_is_to_skip(db):
    six(db)
    f = {x["code"]: x for g in fundresearch.research(db, AS_OF)["groups"] for x in g["funds"]}
    assert f[1]["verdict"] == "consider" and f[6]["verdict"] == "skip" and f[3]["verdict"] in ("fine", "consider")


def test_a_fund_under_three_years_old_is_too_new_to_rank(db):
    six(db)
    add_fund(db, 7, 0.004, years=1.5)
    f = {x["code"]: x for g in fundresearch.research(db, AS_OF)["groups"] for x in g["funds"]}
    assert f[7]["verdict"] == "new" and f[7]["rank"] is None and "less than 3 years" in f[7]["why"]
    assert f[1]["rank"] == [1, 6]          # the new fund does not count in the ranking


def test_the_sentence_has_rank_returns_and_a_worst_fall(db):
    six(db)
    add_fund(db, 8, 0.0022, wobble=0.03)
    f = {x["code"]: x for g in fundresearch.research(db, AS_OF)["groups"] for x in g["funds"]}
    why = f[1]["why"]
    assert "1st of 7" in why and "% a year" in why and "flexi cap" in why.lower()
    assert f[8]["worst_fall"] is not None and f[8]["worst_fall"] > f[1]["worst_fall"]


def test_held_and_watched_funds_are_flagged_and_held_funds_are_never_ideas(db):
    six(db)
    out = fundresearch.research(db, AS_OF, held={"INF001"}, watching={"INF002"})
    f = {x["code"]: x for g in out["groups"] for x in g["funds"]}
    assert f[1]["held"] and f[2]["watching"] and not f[3]["held"]
    assert 1 not in [x["code"] for x in out["ideas"]] and 2 in [x["code"] for x in out["ideas"]]


def test_a_regular_plan_or_a_sectoral_fund_is_not_researched(db):
    six(db)
    add_fund(db, 9, 0.01, plan="Regular Plan")
    add_fund(db, 10, 0.01, category="Equity Scheme - Sectoral/ Thematic")
    codes = {x["code"] for g in fundresearch.research(db, AS_OF)["groups"] for x in g["funds"]}
    assert codes == {1, 2, 3, 4, 5, 6}


def test_cost_appears_when_known_and_is_not_invented_when_not(db):
    six(db)
    db.execute("insert into fund_costs values ('fund 1', ?, 1.2, 0.5, null)", [AS_OF])
    f = {x["code"]: x for g in fundresearch.research(db, AS_OF)["groups"] for x in g["funds"]}
    assert f[1]["ter"] == 0.5 and "0.50%" in f[1]["why"] and f[2]["ter"] is None and "costs" not in f[2]["why"].lower()


def test_each_fund_carries_a_monthly_price_series_for_its_chart(db):
    six(db)
    f = {x["code"]: x for g in fundresearch.research(db, AS_OF)["groups"] for x in g["funds"]}
    assert len(f[1]["spark"]) == 37 and f[1]["spark"][-1] > f[1]["spark"][0] and "_s" not in f[1]


def test_a_top_fund_that_costs_over_one_and_a_half_percent_is_only_fine_and_says_so(db):
    six(db)
    db.execute("insert into fund_costs values ('fund 1', ?, 2.8, 2.1, null)", [AS_OF])
    f = {x["code"]: x for g in fundresearch.research(db, AS_OF)["groups"] for x in g["funds"]}
    assert f[1]["rank"][0] == 1 and f[1]["verdict"] == "fine" and "dear" in f[1]["why"]
    assert 1 not in [x["code"] for x in fundresearch.research(db, AS_OF)["ideas"]]
