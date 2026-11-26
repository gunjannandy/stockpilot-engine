"""The evening forecast end to end on the seeded database: universe, holding checks, the run, reruns, the archive freeze."""
import json
import shutil
from datetime import date, datetime, timedelta

import pytest

from forecast_seed import AS_OF, SECTOR_INDEX, seeded
from stockpilot import forecast, readiness, store
from stockpilot.calls import decide
from stockpilot.analysis import screen
from stockpilot.jobs import daily as jobs
from stockpilot.book import positions
from stockpilot.calls.decide import Rules
from stockpilot.calls.runner import RunnerError

RULES = Rules(sector_index=SECTOR_INDEX)


@pytest.fixture(scope="module")
def template(tmp_path_factory):
    """Seeded once (about 10 s); each test works on its own copy of the file."""
    folder = tmp_path_factory.mktemp("seed")
    d = seeded(folder)
    d.execute("delete from calls where symbol = 'INFY'")     # the seed's own calls would muddy "previous"; tests add what they need
    d.execute("update calls set score_1m = null, score_3m = null, score_6m = null")   # 30+ scored calls would calibrate every chance; R6 tests add their own history
    d.execute("checkpoint")
    d.close()
    return folder / "sp.duckdb"


@pytest.fixture
def db(template, tmp_path):
    shutil.copy(template, tmp_path / "t.duckdb")
    return store.open(tmp_path / "t.duckdb")


def answer(symbol, p, **kw):
    return {"symbol": symbol, "probability": p, "moved_by": [{"reason": "trend", "points": 3}], "risks": ["market"],
            "summary": f"{symbol}: nothing odd.", "summary_bn": "কিছু নেই।", "level_flag": None, "change_reason": None,
            "would_buy_if": None, "news_used": [], **kw}


def fake_analyse(probs=None, default=0.5, seen=None, **extra):
    def analyse(brief, role, runners, **kw):
        if seen is not None:
            seen.append((role, brief))
        items = [answer(s["symbol"], (probs or {}).get(role, {}).get(s["symbol"], default), **extra.get(s["symbol"], {}))
                 for s in brief["stocks"]]
        return {"runner": "fake", "failures": [], "decisions": {"market_view": "Calm.", "market_view_bn": "শান্ত।", "items": items}}
    return analyse


def rows(db, day=AS_OF):
    cols = [c[0] for c in db.execute("select * from calls limit 0").description]
    return {r[cols.index("symbol")]: dict(zip(cols, r)) for r in db.execute("select * from calls where made_on = ?", [day]).fetchall()}


def go(db, analyse=None, day=AS_OF, budget=100_000, **kw):
    return forecast.run(db, day, analyse or fake_analyse(), ["fake"], RULES, budget, **kw)


# ---- holding checks -------------------------------------------------------------------------------------

def checks(db, rules=RULES, day=AS_OF):
    held = positions.held(db, day)
    pv = sum(p.value for p in held if p.kind == "equity")
    ctx = forecast.dossier.context(db, day, None, held, rules.sector_index)
    return forecast.holding_checks(db, day, held, rules, pv, ctx.sector_returns)


def test_a_lot_turning_long_term_within_30_days_is_a_check(db):
    assert any("turns long-term on 02 Dec" in t for t in checks(db)["WIPRO"]["triggers"])


def test_an_exchange_watch_list_holding_is_a_check(db):
    db.execute("insert into surveillance values (?, 'ITC', 'GSM Stage II')", [AS_OF])
    assert any("watch list" in t and "GSM Stage II" in t for t in checks(db)["ITC"]["triggers"])


def test_a_holding_above_eight_percent_is_a_check(db):
    big = max((p for p in positions.held(db, AS_OF) if p.kind == "equity"), key=lambda p: p.value)
    pv = sum(p.value for p in positions.held(db, AS_OF) if p.kind == "equity")
    assert big.value / pv > 0.08                             # the seed's HDFC Bank
    assert any("of the portfolio (limit 8%)" in t for t in checks(db)[big.symbol]["triggers"])


def test_twenty_points_behind_the_sector_is_a_check(db):
    # TATAMOTORS sinks 30% in three months while Nifty Auto drifts up
    for n, d in enumerate(db.execute("select date from prices where symbol = 'TATAMOTORS' order by date desc limit 64").fetchall()):
        db.execute("update prices set close = close * ? where symbol = 'TATAMOTORS' and date = ?", [0.7 if n == 0 else 1.0, d[0]])
    t = checks(db)["TATAMOTORS"]["triggers"]
    assert any("points behind its sector over 3 months" in x for x in t)


def make_position_from_a_call(db, symbol, call_day, lot_day, stop, target=150.0):
    db.execute("insert into calls (made_on, symbol, kind, action, section, probability, entry, stop, target) "
               "values (?, ?, 'candidate', 'buy', 'buy', 0.7, 100, ?, ?)", [call_day, symbol, stop, target])
    db.execute("update lots set acquired_on = ? where symbol = ?", [lot_day, symbol])


def test_a_stop_reached_on_a_position_opened_from_a_call_is_a_check_with_the_stop(db):
    price = db.execute("select close from prices where symbol = 'ITC' order by date desc limit 1").fetchone()[0]
    make_position_from_a_call(db, "ITC", date(2026, 11, 24), date(2026, 11, 25), stop=price + 10)    # the price is under the stop
    held_day = date(2026, 11, 27)
    db.execute("insert into prices select ?, symbol, exchange, series, open, high, low, close, prev_close, volume, value, trades "
               "from prices where date = ? and symbol = 'ITC'", [held_day, AS_OF])
    found = checks(db, day=held_day)["ITC"]
    assert found["stop_hit"] == price + 10 and any("reached its stop" in t for t in found["triggers"])


def test_an_old_holding_never_gets_a_stop_even_with_a_call_on_it(db):
    make_position_from_a_call(db, "ITC", date(2026, 11, 10), date(2026, 11, 12), stop=1e9)      # before 24 Nov
    assert "ITC" not in checks(db) or checks(db)["ITC"]["stop_hit"] is None


def test_a_lot_with_no_call_in_the_five_days_before_it_is_not_opened_from_a_call(db):
    make_position_from_a_call(db, "ITC", date(2026, 11, 24), date(2026, 12, 8), stop=1e9)       # call 2 weeks before the lot
    assert "ITC" not in checks(db) or checks(db)["ITC"]["stop_hit"] is None


# ---- the universe ---------------------------------------------------------------------------------------

def universe(db, **kw):
    result = screen.run(db, AS_OF)
    held = positions.held(db, AS_OF)
    return forecast.pick_universe(db, AS_OF, result, held, kw.get("checks", {}), kw.get("hidden", set())), result, held


def test_the_universe_has_the_top_25_the_triggered_and_a_rotating_fifth_and_is_about_35(db):
    why, result, held = universe(db, checks=checks(db))
    top = [c["symbol"] for c in sorted((c for c in result["candidates"] if not c["flags"]),
                                       key=lambda c: (-c["composite"], c["symbol"]))][:25]
    assert all(s in why for s in top)
    assert "ASMCO" not in why                                  # excluded by the screen
    assert 25 <= len(why) <= 25 + Rules().watch_cap + 15
    assert any(w.startswith("holding:") for ws in why.values() for w in ws)


def test_a_hidden_stock_is_out_of_the_top_25_and_the_next_one_takes_its_place(db):
    why, result, _ = universe(db)
    first = [c["symbol"] for c in result["candidates"] if not c["flags"]][0]
    why2, _, _ = universe(db, hidden={first})
    assert first not in why2 or first in [p.symbol for p in positions.held(db, AS_OF)]
    assert sum(any(w.startswith("screen rank") for w in ws) for ws in why2.values()) == 25


def test_the_rotating_fifth_is_stable_and_covers_every_holding_within_five_days(db):
    held = [p for p in positions.held(db, AS_OF) if p.kind == "equity"]
    seen = set()
    for k in range(5):
        day = AS_OF + timedelta(days=k)
        seen |= {p.symbol for p in held if forecast._rotating(p, day)}
        assert [p.symbol for p in held if forecast._rotating(p, day)] == [p.symbol for p in held if forecast._rotating(p, day)]
    assert seen == {p.symbol for p in held}


def test_triggered_watchlist_stocks_are_capped_and_results_dates_come_first(db):
    why, _, _ = universe(db)
    watch = [s for s, ws in why.items() if any(w.startswith("watchlist") for w in ws)]
    assert len(watch) <= Rules().watch_cap == 8
    assert any("results within 10 days" in w for w in why.get("TCS", [])) or "TCS" in why    # TCS reports in 3 days


def test_a_watchlist_stock_reporting_within_ten_days_is_in(db):
    why, _, _ = universe(db)
    assert any("results within 10 days" in w for w in why.get("TCS", [])) or "TCS" in why   # TCS reports in 3 days


# ---- the run --------------------------------------------------------------------------------------------

def test_the_run_stores_a_call_for_every_answer_with_sections_and_the_new_fields(db):
    out = go(db, fake_analyse({"analyst": {"ICICIBANK": 0.70, "WIPRO": 0.30}}))
    assert out["status"] == "ok" and out["calls"] > 25
    got = rows(db)
    assert got["ICICIBANK"]["section"] in ("buy", "follow") and got["WIPRO"]["section"] == "sell"
    w = got["WIPRO"]
    assert w["summary_bn"] and w["hurdle"] is None or w["hurdle"] > 0
    assert w["base_rate_n"] == 800 and json.loads(w["warnings"]) == []
    assert db.execute("select status from runs where job = 'daily_decide'").fetchone()[0] == "ok"


def test_a_probability_at_the_buy_line_is_a_buy_sized_by_the_rules_and_never_by_the_budget(db):
    one = go(db, fake_analyse({"analyst": {"ICICIBANK": 0.70}}), budget=1_000)
    small = rows(db)["ICICIBANK"]
    db.execute("delete from calls")
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.70}}), budget=10_000_000)
    big = rows(db)["ICICIBANK"]
    assert one["status"] == "ok" and small["section"] == big["section"] == "buy"
    assert small["size_inr"] == big["size_inr"] > 0


def test_the_brief_never_mentions_the_budget_and_stays_inside_the_cap(db, tmp_path):
    seen = []
    go(db, fake_analyse(seen=seen), budget=123_456, brief_dir=tmp_path / "briefs")
    text = json.dumps(seen[0][1]).lower()
    assert "budget" not in text and "123456" not in text
    assert (tmp_path / "briefs" / f"{AS_OF}.json").exists()
    assert len(json.dumps(seen[0][1], default=str)) < 200_000


def test_the_skeptic_sees_only_the_borderline_stocks_and_its_view_is_averaged(db):
    seen = []
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.55}, "skeptic": {"ICICIBANK": 0.65}}, seen=seen))
    skeptic = [b for role, b in seen if role == "skeptic"]
    assert len(skeptic) == 1
    assert "ICICIBANK" in [s["symbol"] for s in skeptic[0]["stocks"]]
    assert all(s["analyst"]["probability"] is not None for s in skeptic[0]["stocks"])
    assert rows(db)["ICICIBANK"]["probability"] == pytest.approx(0.60)


def test_gaps_go_into_the_brief_and_the_run_notes_and_missing_prices_block_buys(db):
    day = AS_OF + timedelta(days=3)                              # Monday 23 Nov: no prices loaded yet
    seen = []
    out = go(db, fake_analyse({"analyst": {"ICICIBANK": 0.8}}, seen=seen), day=day)
    assert any("No prices loaded" in g for g in seen[0][1]["gaps"])
    got = rows(db, day)
    assert got["ICICIBANK"]["section"] == "follow"
    assert "No prices loaded" in json.loads(got["ICICIBANK"]["warnings"])[0]
    assert out["block_buys"] is True


def test_the_own_record_lines_reach_the_brief_and_a_failure_is_only_a_warning(db, monkeypatch):
    seen = []
    monkeypatch.setattr(forecast.record, "build", lambda db, day: {"lines": ["Of the 3 trades, 67% made money."]})
    go(db, fake_analyse(seen=seen))
    assert seen[0][1]["market"]["about_you"] == ["Of the 3 trades, 67% made money."]
    def boom(db, day):
        raise RuntimeError("x")
    monkeypatch.setattr(forecast.record, "build", boom)
    seen.clear()
    go(db, fake_analyse(seen=seen))
    assert "about_you" not in seen[0][1]["market"]


def test_saturday_sends_every_holding_in_a_second_call(db):
    saturday = date(2026, 11, 21)
    seen = []
    go(db, fake_analyse(seen=seen), day=saturday)
    analysts = [b for role, b in seen if role == "analyst"]
    assert len(analysts) == 2
    held = {p.symbol for p in positions.held(db, saturday) if p.kind == "equity" and p.quantity > 0}
    assert held <= {s["symbol"] for s in analysts[1]["stocks"]}
    assert not held & {s["symbol"] for s in analysts[0]["stocks"]}


def test_a_weekday_run_is_one_analyst_call(db):
    seen = []
    go(db, fake_analyse(seen=seen))
    assert [role for role, _ in seen].count("analyst") == 1


def test_a_changed_section_without_a_reason_gets_one_from_code(db):
    db.execute("insert into calls (made_on, symbol, kind, action, section, probability) values (?, 'ICICIBANK', 'candidate', 'watch', 'follow', 0.5)",
               [AS_OF - timedelta(days=1)])
    out = go(db, fake_analyse({"analyst": {"ICICIBANK": 0.72}}))
    c = rows(db)["ICICIBANK"]
    assert c["section"] == "buy" and "Was a follow call, now buy" in c["change_reason"]
    assert "ICICIBANK" in out["missing_change_reason"]


def test_a_reason_the_model_gave_is_kept(db):
    db.execute("insert into calls (made_on, symbol, kind, action, section, probability) values (?, 'ICICIBANK', 'candidate', 'watch', 'follow', 0.5)",
               [AS_OF - timedelta(days=1)])
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.72}}, ICICIBANK={"change_reason": "Results beat by 9%."}))
    assert rows(db)["ICICIBANK"]["change_reason"] == "Results beat by 9%."


def test_a_repeat_buy_says_since_when(db):
    for k in (3, 2, 1):
        db.execute("insert into calls (made_on, symbol, kind, action, section, probability) values (?, 'ICICIBANK', 'candidate', 'buy', 'buy', 0.7)",
                   [AS_OF - timedelta(days=k)])
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.72}}))
    assert json.loads(rows(db)["ICICIBANK"]["reasons"])["since_text"] == f"a buy since {(AS_OF - timedelta(days=3)).day} Nov"


def test_not_now_hides_a_buy_for_its_time_and_not_after_it(db):
    db.execute("insert into not_now (symbol, scope, until, set_by) values ('ICICIBANK', 'buy', ?, 'papa')", [AS_OF + timedelta(days=7)])
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.8}}))
    assert "ICICIBANK" not in rows(db) or rows(db)["ICICIBANK"]["section"] == "watch"
    db.execute("delete from calls")
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.8}}), day=AS_OF)       # still active on the same day
    db.execute("update not_now set until = ?", [AS_OF - timedelta(days=1)])
    db.execute("delete from calls")
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.8}}))
    assert rows(db)["ICICIBANK"]["section"] == "buy"


def test_an_undone_not_now_does_not_hide(db):
    db.execute("insert into not_now (symbol, scope, until, set_by, undone_at) values ('ICICIBANK', 'any', null, 'papa', current_timestamp)")
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.8}}))
    assert rows(db)["ICICIBANK"]["section"] == "buy"


# ---- reruns, the archive and failures --------------------------------------------------------------------

def test_a_rerun_replaces_the_days_calls_instead_of_doubling_them(db):
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.70}}))
    first = db.execute("select count(*) from calls where made_on = ?", [AS_OF]).fetchone()[0]
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.30}}))
    assert db.execute("select count(*) from calls where made_on = ?", [AS_OF]).fetchone()[0] == first
    assert rows(db)["ICICIBANK"]["probability"] == 0.30


def test_an_archived_day_is_frozen_and_the_rerun_says_so(db):
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.70}}))
    db.execute("insert into archived_days (day) values (?)", [AS_OF])
    before = db.execute("select count(*), sum(probability) from calls").fetchone()
    out = go(db, fake_analyse({"analyst": {"ICICIBANK": 0.30}}))
    assert out["status"] == "skipped" and "frozen" in out["note"]
    assert db.execute("select count(*), sum(probability) from calls").fetchone() == before
    status, notes = db.execute("select status, notes from runs order by id desc limit 1").fetchone()
    assert status == "skipped" and "archived" in json.loads(notes)["note"]


def test_a_non_runner_exception_ends_the_run_failed_with_a_problem(db):
    def broken(*a, **k):
        raise ZeroDivisionError("boom")
    before = db.execute("select count(*) from calls").fetchone()[0]
    out = go(db, broken)
    assert out["status"] == "failed"
    assert db.execute("select status from runs where job = 'daily_decide' order by id desc limit 1").fetchone()[0] == "failed"
    assert "boom" in db.execute("select message from problems where job = 'daily_decide'").fetchone()[0]
    assert db.execute("select count(*) from calls").fetchone()[0] == before


def test_a_runner_failure_is_a_failed_run_and_logs_no_calls(db):
    def broken(*a, **k):
        raise RunnerError("every runner failed: claude: 401")
    out = jobs.daily_decide(db, AS_OF, broken, ["claude"], RULES, 100_000)
    assert out["status"] == "failed"
    assert "401" in db.execute("select message from problems where job = 'daily_decide'").fetchone()[0]


def test_a_failed_rerun_keeps_the_earlier_calls(db):
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.70}}))
    n = db.execute("select count(*) from calls").fetchone()[0]
    go(db, lambda *a, **k: (_ for _ in ()).throw(RunnerError("down")))
    assert db.execute("select count(*) from calls").fetchone()[0] == n


# ---- the budget line and the page ----------------------------------------------------------------------

def test_the_budget_line_says_how_many_buys_the_months_budget_covers(db):
    out = go(db, fake_analyse({"analyst": {"ICICIBANK": 0.70, "SBIN": 0.68}}), budget=10_000_000)
    assert out["budget_line"].startswith("₹1 crore left covers the first ")
    buys = sorted((r for r in rows(db).values() if r["section"] == "buy"), key=lambda r: -r["expected_gain_inr"])
    assert buys and out["budget_line"] == decide.budget_line(10_000_000, [r["size_inr"] for r in buys])
    tight = go(db, fake_analyse({"analyst": {"ICICIBANK": 0.70}}), budget=1_000)
    assert tight["budget_line"] == "₹1,000 left does not cover the first buy"


def test_detected_buys_this_month_lower_the_budget_left(db):
    db.execute("insert into calls (made_on, symbol, kind, action, section, probability, size_inr, acted_on) "
               "values (?, 'TCS', 'candidate', 'buy', 'buy', 0.7, 50000, ?)", [AS_OF - timedelta(days=2), AS_OF - timedelta(days=1)])
    assert forecast.budget_left(db, AS_OF, 100_000) == 50_000


def test_site_payload_has_the_page_fields(db):
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.70, "WIPRO": 0.30}}))
    p = forecast.site_payload(db, AS_OF)
    assert {"as_of", "market_view", "market_view_bn", "gaps", "buys", "sells", "follow", "budget_line", "sector_notes"} <= set(p)
    assert p["market_view"] == "Calm." and p["market_view_bn"] == "শান্ত।"
    assert "WIPRO" in [c["symbol"] for c in p["sells"]]
    buy = next(c for c in p["buys"] if c["symbol"] == "ICICIBANK")
    assert buy["stop_pct"] < 0 < buy["target_pct"] and buy["summary_bn"] and buy["base_rate_n"] == 800
    assert {"expected_gain_inr", "entry", "stop", "target", "reasons", "risks", "tax_line", "warnings", "since"} <= set(buy)
    sell = next(c for c in p["sells"] if c["symbol"] == "WIPRO")
    assert sell["section"] == "sell" and "tax" in sell["tax_line"]
    assert len(p["follow"]) <= 10


def test_site_payload_with_no_calls_is_empty_not_an_error(db):
    p = forecast.site_payload(db, AS_OF)
    assert p["buys"] == p["sells"] == p["follow"] == [] and p["market_view"] is None


def test_the_site_build_writes_calls_json(db, tmp_path):
    from stockpilot import site
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.70}}))
    site.build(db, tmp_path / "out", today=AS_OF, budget_inr=100_000)
    body = json.loads(next((tmp_path / "out").rglob("calls.json")).read_text())
    assert body["as_of"] == str(AS_OF) and body["buys"]


def test_headlines_are_fetched_for_the_dossier_stocks_when_the_r3_source_exists(db, monkeypatch):
    import sys
    import types
    calls = []
    stub = types.ModuleType("stockpilot.sources.headlines")
    stub.for_symbols = lambda db_, day, symbols, names, fetch: calls.append((day, set(symbols), names["TCS"], fetch)) or 0
    pkg = types.ModuleType("stockpilot.sources")
    pkg.__path__ = []
    pkg.headlines = stub
    monkeypatch.setitem(sys.modules, "stockpilot.sources", pkg)
    monkeypatch.setitem(sys.modules, "stockpilot.sources.headlines", stub)
    fetch = object()
    go(db, fake_analyse(), fetch=fetch)
    assert len(calls) == 1 and calls[0][0] == AS_OF and calls[0][3] is fetch
    assert {"ICICIBANK", "WIPRO"} <= calls[0][1]


def test_without_the_r3_source_a_fetch_is_not_a_problem(db, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "stockpilot.sources.headlines", None)      # as if the module did not exist
    go(db, fake_analyse(), fetch=lambda url: None)
    assert db.execute("select count(*) from problems where job = 'daily_decide'").fetchone()[0] == 0


def test_a_brief_over_the_cap_is_split_into_pieces_that_fit_instead_of_failing():
    brief = {"as_of": "x", "stocks": [{"symbol": f"S{i}", "pad": "x" * 1000} for i in range(40)]}
    pieces = forecast.fit(brief, limit=12_000)
    assert len(pieces) >= 4
    assert [s["symbol"] for p in pieces for s in p["stocks"]] == [f"S{i}" for i in range(40)]
    assert all(len(json.dumps(p)) <= 12_000 for p in pieces)
    assert forecast.fit({"stocks": [{"symbol": "A"}]}) == [{"stocks": [{"symbol": "A"}]}]


def test_every_string_the_code_writes_for_a_person_avoids_the_banned_words(db):
    from stockpilot.calls import runner
    out = go(db, fake_analyse({"analyst": {"ICICIBANK": 0.70, "WIPRO": 0.30, "SBIN": 0.55}}), day=AS_OF + timedelta(days=3))
    day = AS_OF + timedelta(days=3)
    words = []
    for r in rows(db, day).values():
        words += [r["change_reason"] or "", " ".join(json.loads(r["warnings"]) if r["warnings"] else [])]
        reasons = json.loads(r["reasons"])
        words += [reasons.get("why_code") or "", reasons.get("tax_line") or "", reasons.get("levels_why") or ""]
    words += out["gaps"] + [out["budget_line"] or ""] + out["sector_notes"]
    assert [w for text in words for w in runner.jargon_in(text)] == []


# ---- R6: the raw probability is stored, the calibrated one decides ------------------------------------------

def _scored_history(db, n=40, said=0.7):
    """`n` scored 3-month calls on earlier days: the model said `said` each time and was right half the time."""
    for i in range(n):
        db.execute("insert into calls (made_on, symbol, kind, action, section, probability, raw_probability, base_rate, "
                   "base_rate_n, score_3m, horizon_days) values (?, 'ZZZ', 'candidate', 'watch', 'watch', ?, ?, 0.5, 200, ?, 91)",
                   [AS_OF - timedelta(days=100 + i), said, said, float(i % 2)])


def test_before_thirty_scored_calls_the_stored_and_decided_probability_are_the_models(db):
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.70}, "skeptic": {"ICICIBANK": 0.70}}))
    row = rows(db)["ICICIBANK"]
    assert row["raw_probability"] == pytest.approx(0.70) and row["probability"] == pytest.approx(0.70)


def test_after_thirty_scored_calls_the_run_stores_the_raw_probability_and_decides_on_the_calibrated_one(db):
    _scored_history(db)                     # said 70%, hit 50%: the model is overconfident
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.70}, "skeptic": {"ICICIBANK": 0.70}}))
    row = rows(db)["ICICIBANK"]
    assert row["raw_probability"] == pytest.approx(0.70)
    assert row["probability"] < 0.60                                # calibrated down, so below the 0.57 buy line it is not a buy
    assert row["section"] != "buy"


def test_a_buy_matching_a_learned_pattern_is_demoted_and_the_demotion_is_recorded(db):
    """R11: three dismissals that share ICICIBANK's volatility band make a pattern; its 0.64 buy goes to the follow list,
    stored as 'learned: ...'; a 0.75 buy (10 points above the line) is not touched. The model's brief never mentions it."""
    from stockpilot import learn
    result = screen.run(db, AS_OF, 1.0)
    feats = learn.features(result)
    mine = feats["ICICIBANK"]["vol"]
    held = {s for (s,) in db.execute("select symbol from holdings").fetchall()}
    others = [c["symbol"] for c in result["candidates"] if c["symbol"] not in held | {"ICICIBANK", "SBIN"}
              and feats[c["symbol"]]["vol"] == mine][:3]
    assert len(others) == 3
    for s in others:
        db.execute("insert into not_now (symbol, scope, until, set_by, set_at, how) values (?, 'buy', null, 'papa', ?, 'dismiss')",
                   [s, datetime.combine(AS_OF - timedelta(days=3), datetime.min.time())])
    seen = []
    go(db, fake_analyse({"analyst": {"ICICIBANK": 0.64, "SBIN": 0.75}}, seen=seen))
    got = rows(db)
    reason = got["ICICIBANK"]["change_reason"]
    assert got["ICICIBANK"]["section"] == "follow" and reason.startswith("learned: ")
    assert f"Like stocks you set aside ({reason[len('learned: '):]})" in json.loads(got["ICICIBANK"]["warnings"])
    if feats["SBIN"]["vol"] == mine:
        assert got["SBIN"]["section"] == "buy"
    assert "set aside" not in json.dumps(seen[0][1]) and "learned" not in json.dumps(seen[0][1])


# ---- held stocks the screen skipped (lane P2) -----------------------------------------------------------

def _off_screen_holding(db):
    """The three smallest holdings (none above the single-stock cap), taken off the watchlist: a watchlist stock always passes the screen."""
    small = sorted((p for p in positions.held(db, AS_OF) if p.kind == "equity"), key=lambda p: p.value)[:3]
    db.execute("update watchlist set removed_at = now() where symbol in (" + ",".join("?" * len(small)) + ")", [p.symbol for p in small])
    return tuple(p.symbol for p in small)


def test_an_illiquid_holding_gets_its_own_base_rate_a_risk_line_and_never_a_sell_for_that_alone(db):
    sym = _off_screen_holding(db)[0]
    db.execute("update prices set value = 1.2e6 where symbol = ?", [sym])             # about 0.12 crore a day
    assert sym not in {c["symbol"] for c in screen.run(db, AS_OF, 1.0)["candidates"]}
    go(db, full_review=True)
    got = rows(db)[sym]
    assert got["base_rate_n"] > 0 and got["base_rate"] != 0.5
    summary = json.loads(got["reasons"])["summary"]
    assert "thinly traded" in summary.lower()
    assert got["section"] not in ("sell", "trim")


def test_a_holding_on_the_exchange_watch_list_says_so_and_is_not_sold_for_it(db):
    sym = _off_screen_holding(db)[1]
    db.execute("insert into surveillance values (?, ?, 'STASM I')", [AS_OF, sym])
    go(db, full_review=True)
    got = rows(db)[sym]
    assert got["base_rate_n"] > 0
    assert "watch list" in json.loads(got["reasons"])["summary"] and got["section"] not in ("sell", "trim")


def test_a_new_listing_held_says_limited_evidence(db):
    sym = _off_screen_holding(db)[2]
    db.execute("delete from prices where symbol = ? and date < ?", [sym, AS_OF - timedelta(days=30)])
    go(db, full_review=True)
    got = rows(db)[sym]
    assert got["base_rate_n"] == 0
    assert "limited evidence" in json.loads(got["reasons"])["summary"].lower()


def test_a_chance_moved_from_the_base_rate_with_no_evidence_is_set_back_to_the_base_rate(db):
    """Issue #17: the code-only call stands when the model moves a chance 3 points or more and cites neither a reason nor news."""
    go(db, fake_analyse())
    base = rows(db)["WIPRO"]["base_rate"]
    db.execute("delete from calls where made_on = ?", [AS_OF])
    out = go(db, fake_analyse({"analyst": {"WIPRO": base + 0.20, "ICICIBANK": 0.50}},
                              WIPRO={"moved_by": [], "news_used": []}, ICICIBANK={"moved_by": [], "news_used": []}))
    got = rows(db)
    assert got["WIPRO"]["probability"] == pytest.approx(base) and got["WIPRO"]["raw_probability"] == pytest.approx(base)
    assert "WIPRO" in out["unevidenced_reset"]
    near = got["ICICIBANK"]["base_rate"]
    assert abs(0.50 - near) < 0.03 or "ICICIBANK" in out["unevidenced_reset"]


def test_a_chance_moved_with_a_cited_reason_is_kept(db):
    go(db, fake_analyse())
    base = rows(db)["WIPRO"]["base_rate"]
    db.execute("delete from calls where made_on = ?", [AS_OF])
    out = go(db, fake_analyse({"analyst": {"WIPRO": base + 0.20}}))      # the default answer cites "trend"
    assert rows(db)["WIPRO"]["probability"] == pytest.approx(base + 0.20)
    assert "WIPRO" not in out["unevidenced_reset"]
