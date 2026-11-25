"""Lane M: fund size (AUM), fund chance and reasoning, held fund SIP and call, the contract for funds."""
import json
import math
from datetime import date, timedelta
from pathlib import Path

import pytest

from stockpilot import fundcall, fundresearch, reasoning, store
from stockpilot.sources import fundcosts
from test_fundresearch import AS_OF, CAT, add_fund, six

FIX = Path(__file__).parent / "fixtures" / "amfi"


@pytest.fixture
def db(tmp_path):
    d = store.open(tmp_path / "t.duckdb", job="test")
    yield d
    store.close(d)


def funds_by_code(out):
    return {x["code"]: x for g in out["groups"] for x in g["funds"]}


def rate(db, quartile, n=120, hit=0.64, group="Equity Scheme"):
    db.execute("insert into fund_base_rates values (365, ?, ?, ?, 8, ?, 0.02, 0.6, ?)", [group, quartile, n, hit, AS_OF])


# ---- 1. AUM -------------------------------------------------------------------------------------------

REAL_AUM = FIX / "aum_real_sample.json"


def test_real_amfi_aum_payload_becomes_crore_per_scheme():
    got = fundcosts.parse_aum_api(json.loads(REAL_AUM.read_text())["data"])
    assert got[fundcosts.scheme_key("Axis ELSS Tax Saver Fund - Direct Plan - Growth Option")] == pytest.approx(9753.6808)  # Growth 963579.63 + IDCW 11788.45 lakh: one portfolio, one key
    assert got[fundcosts.scheme_key("360 ONE ELSS Tax Saver Nifty 50 Index Fund - Direct Plan - Growth")] == pytest.approx(51.6309)  # Direct Growth + Direct IDCW, lakh / 100
    # a fund of funds keeps its size in the other column; it is not read as zero
    assert got[fundcosts.scheme_key("Aditya Birla Sun Life Aggressive Hybrid Omni FOF- Direct - IDCW")] > 0
    assert len(got) == 3


def test_aum_refresh_picks_the_latest_quarter_and_an_unreachable_amfi_stores_nothing(db):
    payload = REAL_AUM.read_bytes()
    seen = []

    def fetch(url):
        seen.append(url)
        if "periodId" in url:
            return payload
        return json.dumps({"type": "periods", "data": {"periods": [{"id": 1, "period": "July - September 2026"}]}}).encode()

    assert fundcosts.refresh_aum_api(db, AS_OF, fetch) == 3
    assert "fyId=1&periodId=1" in seen[-1]
    assert db.execute("select aum_cr from fund_costs where key = ?", [fundcosts.scheme_key("Axis ELSS Tax Saver Fund - Direct Plan - Growth Option")]).fetchone()[0] == pytest.approx(9753.6808)
    assert fundcosts.refresh_aum_api(db, AS_OF, lambda url: None) == 0


def test_a_small_fund_is_flagged_and_never_worth_considering(db):
    six(db)
    db.execute("insert into fund_costs values ('fund 1', ?, null, null, 300)", [AS_OF])
    db.execute("insert into fund_costs values ('fund 2', ?, null, null, 5000)", [AS_OF])
    f = funds_by_code(fundresearch.research(db, AS_OF))
    assert f[1]["rank"][0] == 1 and f[1]["small"] is True and f[1]["verdict"] != "consider" and "small" in f[1]["why"].lower()
    assert f[2]["small"] is False and f[2]["verdict"] == "consider"
    assert 1 not in [x["code"] for x in fundresearch.research(db, AS_OF)["ideas"]]


# ---- 2. fund chance and reasoning ---------------------------------------------------------------------------

def test_the_chance_comes_from_the_funds_rank_quartile(db):
    six(db)
    rate(db, 1, n=120, hit=0.64)
    rate(db, 4, n=90, hit=0.41)
    f = funds_by_code(fundresearch.research(db, AS_OF))
    top, bottom = f[1]["reasoning"], f[6]["reasoning"]
    assert top["chance"]["p"] == 0.64 and top["chance"]["n"] == 120 and top["chance"]["base_rate"] == 0.5
    assert bottom["chance"]["p"] == 0.41
    assert "64" in top["chance"]["explain"] and "typical fund" in top["chance"]["explain"]
    assert "chance" not in f[3]["reasoning"]                      # no measured rate for its quartile


def test_fewer_than_thirty_cases_gives_no_chance(db):
    six(db)
    rate(db, 1, n=29)
    assert "chance" not in funds_by_code(fundresearch.research(db, AS_OF))[1]["reasoning"]


def test_every_fund_reasoning_obeys_the_contract_and_has_plain_for_against(db):
    six(db)
    add_fund(db, 7, 0.004, years=1.5)
    rate(db, 1)
    db.execute("insert into fund_costs values ('fund 1', ?, 1.2, 0.5, null)", [AS_OF])
    f = funds_by_code(fundresearch.research(db, AS_OF))
    for x in f.values():
        assert reasoning.contract_errors(x["reasoning"]) == [], x["code"]
    r1, r6, r7 = f[1]["reasoning"], f[6]["reasoning"], f[7]["reasoning"]
    assert r1["stance"] == "buy" and r6["stance"] == "weak" and r7["stance"] == "none"
    assert r1["for"] and all(i["by"] == "code" and i["area"] in reasoning.AREAS for i in r1["for"])
    assert r6["against"] and r1["headline"]
    assert any("0.50%" in i["text"] for i in r1["for"] + r1["against"] + r1["facts"])


def test_every_number_in_the_reasoning_is_in_the_fund_data(db):
    six(db)
    rate(db, 1)
    f = funds_by_code(fundresearch.research(db, AS_OF))[1]
    pool = reasoning.number_pool({k: v for k, v in f.items() if k != "reasoning"}, {"p": 0.64, "n": 120})
    assert reasoning.untraced(f["reasoning"], pool) == []


# ---- 3. held fund, SIP and the weekly call -------------------------------------------------------------

def test_the_sip_names_its_next_date():
    sip = {"amount": 5000, "day": 5, "months": 4}
    assert fundcall.next_sip(sip, date(2026, 11, 20)) == date(2026, 12, 5)
    assert fundcall.next_sip(sip, date(2026, 11, 5)) == date(2026, 11, 5)
    assert fundcall.next_sip({**sip, "day": 31}, date(2026, 11, 20)) == date(2026, 11, 30)    # short month
    assert fundcall.next_sip(None, date(2026, 11, 20)) is None


def test_a_sip_found_in_trades_carries_its_next_date(db):
    six(db)
    for m in (8, 9, 10, 11):
        db.execute("insert into trades (trade_key, kind, isin, side, trade_date, quantity, price) values (?, 'mf', 'INF001', 'buy', ?, 100, 50)",
                   [f"k{m}", date(2026, m, 5)])
    sip = fundcall.sip_schedule(db, "INF001", AS_OF)
    assert sip["amount"] == 5000 and sip["next"] == "2026-12-05"


def test_calls_name_the_fund_so_the_pane_can_find_them():
    c = {"row": {"name": "F", "isin": "INF001", "category": CAT, "judged": False, "base_rate": None, "sip": None}, "model": None, "call": "Keep",
         "line": "Nothing to do.", "screen": {"call": "Keep"}}
    e = fundcall._entry(c)
    assert e["isin"] == "INF001"


def test_a_held_fund_gets_its_call_and_sip_in_the_reasoning(db):
    six(db)
    rate(db, 1)
    out = fundresearch.research(db, AS_OF, held={"INF001"})
    calls = [{"isin": "INF001", "call": "Add", "line": "Add. Keep your SIP of ₹5,000 a month going.",
              "sip": {"amount": 5000, "day": 5, "months": 4, "next": "2026-12-05"}}]
    fundresearch.attach_calls(out, calls)
    f = funds_by_code(out)[1]
    assert f["call"] == "Add" and f["sip"]["next"] == "2026-12-05"
    assert f["reasoning"]["stance"] == "buy" and "Add" in f["reasoning"]["headline"]
    assert reasoning.contract_errors(f["reasoning"]) == []
    assert "call" not in funds_by_code(out)[2]


def test_the_saturday_run_makes_fund_calls():
    import inspect
    from stockpilot.jobs import weekly
    assert "fundcall.run" in inspect.getsource(weekly.run)


def test_the_site_writes_fund_research_with_reasoning(tmp_path):
    from seed_site import AS_OF as SITE_DAY, seed
    from stockpilot import site
    db = seed(tmp_path / "sp.duckdb")
    site.build(db, tmp_path / "site", today=SITE_DAY, budget_inr=100000)
    body = json.loads((tmp_path / "site" / "data" / "fund_research.json").read_text())
    funds = [f for g in body["groups"] for f in g["funds"]]
    assert all(reasoning.contract_errors(f["reasoning"]) == [] for f in funds)
