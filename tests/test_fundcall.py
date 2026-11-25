"""R13: the weekly fund forecaster. Synthetic NAV history (16 funds with steady, distinct growth so ranks persist),
a faked model, no network."""
import json
from datetime import date, timedelta

import pytest

from stockpilot import backup, fundcall, store

from stockpilot.sources import fundcosts

from stockpilot.calls import runner

AS_OF = date(2026, 11, 21)         # a Saturday
CAT = "Equity Scheme - Flexi Cap Fund"
MONTHS = 72


def isin(code):
    return f"INF{code:03d}"


def _nav_dates(months):
    out = []
    for k in range(months, 0, -1):
        y, m = divmod(AS_OF.year * 12 + AS_OF.month - 1 - k, 12)
        out.append((k, date(y, m + 1, 20)))
    return out + [(0, AS_OF)]


def seed_fund(db, code, g, months=MONTHS, category=CAT, plan="Direct Plan", name=None, ter=None, aum=5000.0):
    name = name or f"Test Fund {code:02d}"
    db.execute("insert into funds values (?, ?, null, ?, ?, 'Growth', ?, 'House')", [code, isin(code), name, plan, category])
    for k, day in _nav_dates(months):
        db.execute("insert into navs values (?, ?, ?)", [day, code, 100 * (1 + g) ** (months - k)])
    if ter is not None or aum is not None:
        regular, direct = (ter, None) if plan.startswith("Regular") else (None, ter)
        db.execute("insert into fund_costs values (?, ?, ?, ?, ?)", [fundcosts.scheme_key(name), AS_OF.replace(day=1), regular, direct, aum])


def seed_twins(db):
    """A Regular plan and its Direct twin share one AMFI cost row (the key drops the plan words)."""
    seed_fund(db, 30, 0.007, plan="Regular Plan", name="Twin Fund Regular", ter=None, aum=None)
    seed_fund(db, 31, 0.0072, plan="Direct Plan", name="Twin Fund Direct", ter=None, aum=None)
    db.execute("insert into fund_costs values (?, ?, 1.9, 0.6, 5000)", [fundcosts.scheme_key("Twin Fund Direct"), AS_OF.replace(day=1)])


def add_navs(db, days):
    """Daily NAVs on exact days for funds 1-16, on the same growth curve, so a window has prices at both ends."""
    start = _nav_dates(MONTHS)[0][1]
    for code in range(1, 17):
        for d in days:
            db.execute("insert or replace into navs values (?, ?, ?)",
                       [d, code, 100 * (1 + 0.004 + 0.0006 * code) ** ((d - start).days / 30.44 + 1)])


def nav_now(db, code):
    return db.execute("select nav from navs where scheme_code = ? and date = ?", [code, AS_OF]).fetchone()[0]


def hold(db, code, qty=100.0, cost_ratio=0.97, bought=AS_OF - timedelta(days=800)):
    db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, source) values "
               "('mf', ?, ?, ?, ?, ?, 'test')", [isin(code), isin(code), bought, qty, nav_now(db, code) * cost_ratio])


@pytest.fixture
def db(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    for i in range(1, 17):                                   # fund 16 is the best, fund 1 the worst
        seed_fund(db, i, 0.004 + 0.0006 * i, ter=1.2 - 0.045 * i)      # the better funds also cost less
    return db


class Model:
    """Answers the fund_forecast role: per id a (chance, stance, reason); anything unnamed gets 0.5 / keep."""
    def __init__(self, answers=None, fail=False):
        self.answers, self.fail, self.briefs = answers or {}, fail, []

    def __call__(self, brief, role, runners, **kw):
        assert role == "fund_forecast"
        self.briefs.append(brief)
        if self.fail:
            raise runner.RunnerError("every runner failed")
        items = []
        for f in brief["funds"]:
            p, stance, reason = self.answers.get(f["name"], (0.5, "keep", "Nothing stands out."))
            items.append({"id": f["id"], "probability": p if f["base_rate"] else None, "stance": stance,
                          "moved_by": [{"reason": "trend", "points": 1}], "risks": ["markets fall"], "reason": reason})
        return {"runner": "fake", "failures": [], "decisions": {"items": items}}


def run(db, model=None, **kw):
    model = model or Model()
    out = fundcall.run(db, AS_OF, model, ["fake"], **kw)
    return out, model


def calls(db):
    return {r[0]: r for r in db.execute("select name, call, code_call, model_stance, probability, base_rate, base_rate_n, line "
                                        "from fund_calls where made_on = ?", [AS_OF]).fetchall()}


# ---- the base rate --------------------------------------------------------------------------------------

def test_base_rate_is_measured_on_the_navs_we_hold(db):
    rates = fundcall.base_rates(db, AS_OF)
    top, bottom = rates[("Equity Scheme", 1)], rates[("Equity Scheme", 4)]
    assert top["hit_rate"] == 1.0 and bottom["hit_rate"] == 0.0           # steady funds keep their rank
    assert top["n"] >= fundcall.MIN_N and top["periods"] >= fundcall.MIN_PERIODS
    assert top["avg_excess"] > 0 > bottom["avg_excess"]
    assert top["cost_drag"] == pytest.approx(sum(1.2 - 0.045 * i for i in (13, 14, 15, 16)) / 4)   # the top quartile's average yearly cost
    fundcall.save_base_rates(db, rates, AS_OF)
    assert db.execute("select count(*) from fund_base_rates").fetchone()[0] == 4
    # saving again replaces, not adds
    fundcall.save_base_rates(db, rates, AS_OF)
    assert db.execute("select count(*) from fund_base_rates").fetchone()[0] == 4


def test_a_zero_nav_row_from_a_wound_up_fund_is_not_a_price(db):
    before = fundcall.base_rates(db, AS_OF)
    code = db.execute("select min(scheme_code) from funds").fetchone()[0]
    db.execute("update navs set nav = 0 where scheme_code = ? and date = (select date from navs where scheme_code = ? "
               "order by date limit 1 offset 36)", [code, code])
    after = fundcall.base_rates(db, AS_OF)              # used to divide by zero on the live store (Franklin, Bandhan rows)
    assert set(after) == set(before)


def test_short_history_refuses_a_rate_and_says_so_on_the_call(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    for i in range(1, 17):                                    # 40 months: enough for a 3-year rank, not for a measured rate
        seed_fund(db, i, 0.004 + 0.0006 * i, months=40, ter=0.8)
    hold(db, 16)
    assert fundcall.base_rates(db, AS_OF) == {}
    out, model = run(db)
    row = calls(db)["Test Fund 16"]
    assert row[5] is None and row[6] is None                  # no rate stored, none invented
    assert "Not enough price history on file" in row[7] and "no rate is given" in row[7]
    assert model.briefs[0]["funds"][0]["base_rate"] is None   # the model is told there is none
    assert all(a is None for a in [row[4]])                   # and gives no chance


# ---- each call -----------------------------------------------------------------------------------------

def test_add_for_a_top_fund_with_the_model_agreeing_and_a_sip(db):
    hold(db, 16)
    for month in range(1, 5):                                 # 4 monthly buys of 5000
        db.execute("insert into trades (trade_key, source, kind, symbol, isin, side, trade_date, quantity, price) "
                   "values (?, 'coin', 'mf', ?, ?, 'buy', ?, 50, 100)", [f"k{month}", isin(16), isin(16), AS_OF - timedelta(days=30 * month - 3)])
    out, _ = run(db, Model({"Test Fund 16": (0.75, "add", "A steady record at a low cost.")}))
    row = calls(db)["Test Fund 16"]
    assert row[1] == "Add" and row[2] == "Add" and row[3] == "add"
    assert "Keep your SIP of ₹5,000 a month" in row[7] and "1 of 16" in row[7] and "100%" in row[7]


def test_add_without_a_sip_names_no_amount(db):
    hold(db, 16)
    run(db, Model({"Test Fund 16": (0.75, "add", "A steady record at a low cost.")}))
    line = calls(db)["Test Fund 16"][7]
    assert "No SIP is on file" in line and "₹" not in line.split("No SIP is on file")[1]


def test_keep_is_nothing_to_do_and_costs_no_model_call(db):
    hold(db, 12)                                              # rank 5 of 16: not top quarter, not bottom half
    out, model = run(db)
    row = calls(db)["Test Fund 12"]
    assert row[1] == "Keep" and row[7].startswith("Nothing to do.")
    assert model.briefs == [] and out["asked_model"] is False


def test_stop_adding_for_the_lower_half_and_pauses_the_sip(db):
    hold(db, 7)                                               # rank 10 of 16
    for month in range(1, 5):
        db.execute("insert into trades (trade_key, source, kind, symbol, isin, side, trade_date, quantity, price) "
                   "values (?, 'coin', 'mf', ?, ?, 'buy', ?, 20, 250)", [f"s{month}", isin(7), isin(7), AS_OF - timedelta(days=30 * month - 3)])
    run(db, Model({"Test Fund 07": (0.4, "stop_adding", "It has lagged for years.")}))
    row = calls(db)["Test Fund 07"]
    assert row[1] == "Stop adding" and "Pause the ₹5,000 monthly SIP" in row[7]


def test_a_switch_shows_the_tax_the_exit_load_and_the_cost_saved(db):
    hold(db, 1)                                               # the worst fund, 3% gain, long-term
    out, model = run(db, Model({"Test Fund 01": (0.2, "switch", "It keeps trailing its peers.")}))
    row = calls(db)["Test Fund 01"]
    assert row[1] == "Switch"
    line = row[7]
    assert "Switching to Test Fund 16" in line and "in tax" in line and "long-term gain" in line
    assert "exit load" in line and "a year in fund charges" in line and "0.68 points less" in line
    d = json.loads(db.execute("select detail from fund_calls where name = 'Test Fund 01'").fetchone()[0])
    assert d["switch"]["tax"] > 0 and d["switch"]["saved_inr"] > 0
    cat = db.execute("select category from funds where name = 'Test Fund 16'").fetchone()[0]
    assert cat == CAT                                         # same category only
    brief_fund = model.briefs[0]["funds"][0]
    assert brief_fund["alternative"]["name"] == "Test Fund 16"


def test_the_exit_load_is_used_when_the_owner_supplies_it(db):
    hold(db, 1, bought=AS_OF - timedelta(days=200), cost_ratio=0.99)        # young lots, tiny gain
    run(db, Model({"Test Fund 01": (0.2, "switch", "It keeps trailing its peers.")}), exit_loads={isin(1): 1.0})
    line = calls(db)["Test Fund 01"][7]
    assert "exit load about ₹" in line and "not on file" not in line


def test_a_switch_that_costs_too_much_tax_is_a_review_that_says_why(db):
    hold(db, 1, cost_ratio=0.5, bought=AS_OF - timedelta(days=100))        # a big short-term gain
    run(db, Model({"Test Fund 01": (0.2, "switch", "It keeps trailing its peers.")}))
    row = calls(db)["Test Fund 01"]
    assert row[1] == "Review" and row[2] == "Review"
    assert "more than 2% of the holding" in row[7] and "in tax and exit load" in row[7]


def test_a_switch_without_a_known_saving_is_a_review(db):
    for i in (13, 14, 15, 16):                                 # no cost on file for any top-quarter peer
        db.execute("delete from fund_costs where key = ?", [fundcosts.scheme_key(f"Test Fund {i}")])
    hold(db, 1)
    run(db, Model({"Test Fund 01": (0.2, "switch", "It keeps trailing its peers.")}))
    row = calls(db)["Test Fund 01"]
    assert row[1] == "Review" and row[2] == "Review"          # no peer with a known cost to point to, so no switch


def test_a_regular_plan_switches_to_its_own_direct_twin(db):
    seed_twins(db)
    hold(db, 30)
    run(db, Model({"Twin Fund Regular": (0.4, "switch", "Same fund, lower cost.")}))
    row = calls(db)["Twin Fund Regular"]
    assert row[1] == "Switch" and "Switching to Twin Fund Direct" in row[7] and "1.30 points less" in row[7]


# ---- the two views, neither rubber-stamping ------------------------------------------------------------

def test_the_model_can_veto_a_switch_and_an_add(db):
    hold(db, 1)
    hold(db, 16)
    run(db, Model({"Test Fund 01": (0.8, "keep", "It may recover."), "Test Fund 16": (0.5, "review", "It is already priced in.")}))
    got = calls(db)
    assert got["Test Fund 01"][1] == "Review" and got["Test Fund 01"][2] == "Switch" and "did not back switching" in got["Test Fund 01"][7]
    assert got["Test Fund 16"][1] == "Keep" and got["Test Fund 16"][2] == "Add"


def test_the_model_cannot_create_an_add_or_a_switch(db):
    hold(db, 12)
    assert fundcall.combine("Keep", {"probability": 0.99, "stance": "add"}, True) == ("Keep", "")
    assert fundcall.combine("Keep", {"probability": 0.0, "stance": "switch"}, True) == ("Review", "The model sees a weak year ahead for it.")
    assert fundcall.combine("Stop adding", {"probability": 0.7, "stance": "keep"}, True)[0] == "Keep"
    assert fundcall.combine("Stop adding", {"probability": None, "stance": "keep"}, False)[0] == "Stop adding"


def test_with_no_model_nothing_moves_money_on_the_screen_alone(db):
    hold(db, 1)
    hold(db, 16)
    hold(db, 7)
    out, _ = run(db, Model(fail=True))
    got = calls(db)
    assert got["Test Fund 01"][1] == "Review" and got["Test Fund 16"][1] == "Keep" and got["Test Fund 07"][1] == "Stop adding"
    assert "did not weigh in" in got["Test Fund 01"][7]
    assert out["failures"] and out["asked_model"] is True


def test_the_model_chance_stays_near_the_base_rate(db):
    hold(db, 16)
    run(db, Model({"Test Fund 16": (0.02, "add", "A steady record at a low cost.")}))
    row = calls(db)["Test Fund 16"]
    assert row[4] == pytest.approx(row[5] - fundcall.MODEL_MOVE_MAX, abs=1e-3) or row[4] >= 0.02
    assert row[4] >= row[5] - fundcall.MODEL_MOVE_MAX - 1e-9


def test_a_model_sentence_with_digits_or_jargon_is_dropped(db):
    hold(db, 16)
    run(db, Model({"Test Fund 16": (0.7, "add", "It will make 15% next year.")}))
    assert "15%" not in calls(db)["Test Fund 16"][7]
    for word in runner.banned_words()[:3]:
        assert word not in calls(db)["Test Fund 16"][7].lower()


# ---- the brief, the schema, the record, the payload --------------------------------------------------------

def test_the_brief_holds_no_personal_data(db):
    hold(db, 1, qty=7777.0, cost_ratio=0.91)
    for month in range(1, 5):
        db.execute("insert into trades (trade_key, source, kind, symbol, isin, side, trade_date, quantity, price) "
                   "values (?, 'coin', 'mf', ?, ?, 'buy', ?, 123.45, 100)", [f"p{month}", isin(1), isin(1), AS_OF - timedelta(days=30 * month - 3)])
    _, model = run(db)
    text = json.dumps(model.briefs, default=str)
    assert "7777" not in text and "12345" not in text and "value" not in text and "lots" not in text and "sip" not in text.lower()
    assert "tax" not in text.lower().replace("code_why", "")
    keys = set(model.briefs[0]["funds"][0])
    assert keys == {"id", "name", "category", "rank", "ret_3y", "ret_1y", "consistency", "ter", "aum_cr", "small", "base_rate",
                    "code_call", "code_why", "alternative"}


def test_the_schema_accepts_an_answer_and_refuses_a_bad_one():
    schema = json.loads((runner.ROOT / "schemas" / "fund_forecast.schema.json").read_text())
    good = {"items": [{"id": "F1", "probability": 0.6, "stance": "keep", "moved_by": [{"reason": "cost", "points": -2}],
                       "risks": ["markets fall"], "reason": "Nothing stands out."}]}
    assert runner.schema_errors(good, schema) == []
    assert runner.schema_errors({"items": [{**good["items"][0], "probability": None}]}, schema) == []
    assert runner.schema_errors({"items": [{**good["items"][0], "probability": 1.4}]}, schema)
    assert runner.schema_errors({"items": [{"id": "F1"}]}, schema)
    assert runner.schema_path("fund_forecast").name == "fund_forecast.schema.json"
    assert (runner.PROMPTS / "fund_forecast.md").exists()


def test_the_runner_is_used_with_the_fund_role(db, monkeypatch):
    hold(db, 1)
    seen = {}

    def fake_run(cmd, **kw):
        class Done:
            returncode, stderr = 0, ""
            stdout = json.dumps({"structured_output": {"items": []}})
        seen["prompt"] = kw.get("input") or cmd[2]
        return Done()
    got = runner.analyse({"funds": []}, "fund_forecast", ["claude"], env={"CLAUDE_CODE_OAUTH_TOKEN": "x"}, run=fake_run)
    assert got["decisions"] == {"items": []} and "weekly fund review" in seen["prompt"]


def test_calls_are_scored_against_the_category_middle(db):
    hold(db, 16)
    hold(db, 1)
    run(db, Model({"Test Fund 16": (0.75, "add", "A steady record at a low cost."), "Test Fund 01": (0.2, "switch", "It keeps trailing.")}))
    db.execute("update fund_calls set made_on = ? where call in ('Add', 'Switch', 'Review')", [AS_OF - timedelta(days=200)])
    add_navs(db, [AS_OF - timedelta(days=d) for d in (200, 170, 109, 18)])      # prices at both ends of each window
    assert fundcall.score(db, AS_OF) > 0
    rows = {r[0]: r[1:] for r in db.execute("select call, score_1m, score_3m, score_6m from fund_calls").fetchall()}
    assert rows["Add"] == (1.0, 1.0, 1.0)                     # the best fund beat the middle fund
    assert rows["Switch"] == (1.0, 1.0, 1.0)                  # the fund it pointed to beat the one held
    s = fundcall.summary(db)
    assert s["unproven"] is True and s["by_call"]["Add"]["right"] == 1.0


def test_a_switch_to_the_same_funds_direct_plan_is_not_scored(db):
    seed_twins(db)
    hold(db, 30)
    run(db, Model({"Twin Fund Regular": (0.4, "switch", "Same fund, lower cost.")}))
    db.execute("update fund_calls set made_on = ?", [AS_OF - timedelta(days=200)])
    add_navs(db, [AS_OF - timedelta(days=d) for d in (200, 170, 109, 18)])
    fundcall.score(db, AS_OF)
    assert db.execute("select score_3m from fund_calls where name = 'Twin Fund Regular'").fetchone() == (None,)


def test_site_payload_and_the_portfolio_list_gain_additive_keys(db):
    hold(db, 16)
    hold(db, 1)
    hold(db, 12)
    run(db, Model({"Test Fund 16": (0.75, "add", "A steady record at a low cost."), "Test Fund 01": (0.2, "switch", "It keeps trailing.")}))
    payload = fundcall.site_payload(db)
    assert payload["as_of"] == str(AS_OF) or payload["as_of"] == AS_OF
    by = {c["name"]: c for c in payload["calls"]}
    assert by["Test Fund 16"]["call"] == "Add" and by["Test Fund 12"]["call"] == "Keep"
    assert set(by["Test Fund 01"]) >= {"name", "verdict", "why", "call", "line", "code_call", "base_rate", "chance", "switch", "sip"}
    assert by["Test Fund 01"]["verdict"] == by["Test Fund 01"]["call"] and by["Test Fund 01"]["why"] == by["Test Fund 01"]["line"]
    assert payload["base_rates"] and "alive today" in payload["base_rate_caveat"] and payload["record"]["unproven"]
    from stockpilot import site
    assert site.weekly_view(db, "funds")[0]["name"]
    assert all(not runner.jargon_in(c["line"]) for c in payload["calls"])


def test_the_site_writes_funds_json(tmp_path):
    from seed_site import AS_OF as SITE_DAY, seed
    from stockpilot import site
    db = seed(tmp_path / "sp.duckdb")
    site.build(db, tmp_path / "site", today=SITE_DAY, budget_inr=100000)
    body = json.loads((tmp_path / "site" / "data" / "funds.json").read_text())
    assert set(body) >= {"as_of", "headline", "calls", "base_rates", "base_rate_caveat", "record"}


def test_the_new_tables_are_in_a_backup_list():
    assert "fund_calls" in backup.STATE_TABLES and backup.SEQUENCES["fund_calls"] == "fund_call_id"
    assert "fund_base_rates" in backup.MARKET_TABLES


def test_nothing_in_the_module_can_place_an_order():
    import inspect
    text = inspect.getsource(fundcall)
    for banned in ("place_order", "kite.", "requests.post", "urlopen", "subprocess"):
        assert banned not in text


def test_the_saturday_job_makes_the_fund_calls_with_the_lock_free(tmp_path):
    from datetime import datetime
    from fakes import make_machine
    from stockpilot.jobs import weekly as job
    m = make_machine(tmp_path, now=datetime(2026, 11, 21, 10, 3))
    with m.db("seed") as db:
        for i in range(1, 17):
            seed_fund(db, i, 0.004 + 0.0006 * i, ter=1.2 - 0.045 * i)
        hold(db, 16)
    model, held = Model({"Test Fund 16": (0.75, "add", "A steady record at a low cost.")}), []
    m.analyse = lambda b, role, rs: held.append(store.holder(m.db_path)) or model(b, role, rs)
    result = job.run(m, datetime(2026, 11, 21, 10, 3), analyse_only=True)
    assert any(n.startswith("fund calls: 1 funds") for n in result["notes"])
    assert held == [None]                                     # the model ran with the database lock released
    with m.db("check") as db:
        assert db.execute("select call from fund_calls").fetchall() == [("Add",)]


def test_a_failing_fund_step_is_a_problem_and_the_weekly_review_stands(tmp_path):
    from datetime import datetime
    from fakes import make_machine
    from stockpilot.jobs import weekly as job
    m = make_machine(tmp_path, now=datetime(2026, 11, 21, 10, 3))
    m.analyse = lambda b, role, rs: (_ for _ in ()).throw(ValueError("boom"))
    with m.db("seed") as db:
        for i in range(1, 17):
            seed_fund(db, i, 0.004 + 0.0006 * i, ter=0.8)
        hold(db, 1)
    result = job.run(m, datetime(2026, 11, 21, 10, 3), analyse_only=True)
    assert any("fund calls failed" in n for n in result["notes"])
    with m.db("check") as db:
        assert db.execute("select count(*) from problems where message like 'fund calls%'").fetchone()[0] == 1
        assert db.execute("select count(*) from weekly_reports where section = 'funds'").fetchone()[0] == 1
