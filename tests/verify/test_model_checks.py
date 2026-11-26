"""Checks 7 to 11 on hand-built stores: a clean one that passes and a deliberately broken one that each check catches."""
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from vhelpers import DAY, price_rows
from helpers import insert_prices
from stockpilot.analysis import screen
from stockpilot.verify import Ctx, model

ROOT = Path(__file__).resolve().parents[2]


def ctx_for(db, root=ROOT, **kw):
    return Ctx(db=db, day=DAY, root=root, **kw)


def call(db, symbol, section, p=0.55, base=0.5, n=500, made=DAY, entry=100.0, stop=90.0, target=120.0, size=0.0, horizon=91,
         summary="Profit up 12%; a fair price.", sell_kind=None, broken=None, moved=None, news=None, kind="candidate"):
    reasons = {"summary": summary, "sell_kind": sell_kind, "broken_reason": broken,
               "moved_by": [{"reason": "profit up 12%", "points": 3}] if moved is None else moved}
    db.execute("insert into calls (made_on, symbol, kind, action, probability, base_rate, horizon_days, entry, stop, target, size_inr, reasons, "
               "risks, news, runner, unproven, section, expected_gain_inr, base_rate_n) values "
               "(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?, 'claude', true, ?, 1000, ?)",
               [made, symbol, kind, section, p, base, horizon, entry, stop, target, size, json.dumps(reasons),
                json.dumps(news if news is not None else []), section, n])


def hold(db, symbol, qty, price=100.0, passive=False):
    isin = "INE" + symbol.ljust(6, "0")[:6] + "01"
    db.execute("insert into stocks values (?, ?, 'X', ?)", [symbol, symbol, isin])
    db.execute("insert into holdings values ('2026-11-20 18:00:00', 'equity', ?, ?, ?, ?, 'kite')", [symbol, isin, qty, price])
    db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, source) values ('stock', ?, ?, '2024-01-02', ?, ?, 'tradebook')",
               [symbol, isin, qty, price])
    insert_prices(db, price_rows(symbol, [price] * 3))


# ---- 7 -----------------------------------------------------------------------------------------------------

@pytest.fixture
def screened(db):
    for sym in ("AAA", "BBB", "CCC"):
        insert_prices(db, price_rows(sym, [100.0 + i * 0.1 for i in range(260)]))
        db.execute("insert into stocks values (?, ?, 'X', ?)", [sym, sym, "INE" + sym])
    return db


def test_check7_passes_on_clean_calls_and_a_deterministic_screen(screened):
    call(screened, "AAA", "buy")
    call(screened, "BBB", "follow", p=0.52)
    r = model.check_bounds(ctx_for(screened))
    assert r.status == "pass", r.problems
    assert r.numbers["deterministic"] is True


def test_check7_catches_chance_out_of_bounds_thin_base_rate_and_no_horizon(screened):
    call(screened, "AAA", "buy", p=0.99)
    call(screened, "BBB", "follow", n=12)
    call(screened, "CCC", "follow", horizon=0)
    r = model.check_bounds(ctx_for(screened))
    text = " ".join(r.problems)
    assert r.status == "fail" and "AAA: chance 0.99" in text and "BBB: its base rate rests on 12" in text and "CCC: the call states no horizon" in text


LIMITED_TEXT = "Profit up 12%. Limited evidence: too little price history to say how stocks like this usually do."


def test_check7_accepts_a_held_stock_with_no_history_when_the_call_says_limited_evidence(screened):
    call(screened, "AAA", "hold", kind="holding", base=0.5, n=0, summary=LIMITED_TEXT)
    call(screened, "BBB", "hold", kind="holding", base=0.5, n=12, summary=LIMITED_TEXT)
    r = model.check_bounds(ctx_for(screened))
    assert r.status == "pass", r.problems


def test_check7_still_fails_a_held_stock_with_thin_evidence_that_does_not_say_so(screened):
    call(screened, "AAA", "hold", kind="holding", base=0.5, n=0)
    r = model.check_bounds(ctx_for(screened))
    assert r.status == "fail" and "AAA" in " ".join(r.problems) and "limited evidence" in " ".join(r.problems)


def test_check7_gives_no_such_pass_to_a_stock_that_is_not_held(screened):
    call(screened, "AAA", "follow", kind="candidate", base=0.5, n=0, summary=LIMITED_TEXT)
    assert model.check_bounds(ctx_for(screened)).status == "fail"


def test_check8_passes_a_held_stock_with_no_cases_that_says_limited_evidence(db, tmp_path):
    _buckets(db, 0.46, 0.44)
    call(db, "AAA", "hold", kind="holding", base=0.5, n=0, summary=LIMITED_TEXT)
    assert model.check_calibration(ctx_for(db, _backtest_root(tmp_path), run_backtest=False)).status == "pass"


def test_check7_catches_a_screen_that_differs_between_two_runs(screened, monkeypatch):
    call(screened, "AAA", "buy")
    real, count = screen._compute, {"n": 0}

    def flaky(*a, **k):
        count["n"] += 1
        out = real(*a, **k)
        out["noise"] = count["n"]
        return out
    monkeypatch.setattr(screen, "_compute", flaky)
    r = model.check_bounds(ctx_for(screened))
    assert r.status == "fail" and "different output" in " ".join(r.problems)


def test_check7_ignores_float_noise_in_the_sixteenth_digit_but_catches_a_changed_number(screened, monkeypatch):
    call(screened, "AAA", "buy")
    real, count = screen._compute, {"n": 0}

    def noisy(*a, **k):
        count["n"] += 1
        out = real(*a, **k)
        for c in out["candidates"]:
            c["composite"] += 1e-15 * count["n"]
        return out
    monkeypatch.setattr(screen, "_compute", noisy)
    assert model.check_bounds(ctx_for(screened)).status == "pass"

    def moved(*a, **k):
        count["n"] += 1
        out = real(*a, **k)
        out["candidates"][0]["composite"] += 1e-4 * count["n"]
        return out
    monkeypatch.setattr(screen, "_compute", moved)
    assert model.check_bounds(ctx_for(screened)).status == "fail"


# ---- 8 -----------------------------------------------------------------------------------------------------

def _backtest_root(tmp_path, hit=0.45, n=500):
    docs = tmp_path / "docs"
    docs.mkdir()
    rows = "\n".join(f"| {m} | nifty_up | calm | large | {n:,} | {hit * 100:.1f}% | +1.00% |" for m in (0, 1)) + "\n"
    (docs / "backtest.md").write_text("| Momentum | Regime | Volatility | Liquidity | n | Hit rate | Avg excess |\n|---|---|---|---|---|---|---|\n" + rows)
    return tmp_path


def _buckets(db, hit0, hit1, n0=500, n1=500):
    db.execute("insert into base_rate_buckets values (91, 0, 'nifty_up', 'calm', 'large', ?, ?, 0.01, '2026-11-20'), "
               "(91, 1, 'nifty_up', 'calm', 'large', ?, ?, 0.01, '2026-11-20')", [n0, hit0, n1, hit1])


def test_check8_passes_when_buckets_are_stable(db, tmp_path):
    _buckets(db, 0.46, 0.44)
    r = model.check_calibration(ctx_for(db, _backtest_root(tmp_path), run_backtest=False))
    assert r.status == "pass" and r.hard is False


def test_check8_soft_fails_on_a_moved_bucket_and_names_calls_without_limited_evidence(db, tmp_path):
    _buckets(db, 0.60, 0.44)                               # bucket 0 moved 15 points
    call(db, "AAA", "buy", base=0.6, n=500, summary="Profit up 12%.")
    call(db, "BBB", "buy", base=0.6, n=500, summary="Profit up 9%; limited evidence behind the base rate.")
    r = model.check_calibration(ctx_for(db, _backtest_root(tmp_path), run_backtest=False))
    text = " ".join(r.problems)
    assert r.status == "fail" and not r.blocks            # soft: it never stops a deploy
    assert "hit rate moved +15.0 points" in text and "AAA: its base rate" in text and "BBB: its base rate" not in text


def test_check8_soft_fails_when_a_bucket_sample_falls_below_30(db, tmp_path):
    _buckets(db, 0.45, 0.45, n0=12)
    r = model.check_calibration(ctx_for(db, _backtest_root(tmp_path), run_backtest=False))
    assert r.status == "fail" and "only 12 cases" in " ".join(r.problems)


def test_the_real_baseline_table_parses_to_forty_buckets():
    assert len(model.baseline_buckets(ROOT / "docs" / "backtest.md")) == 40


# ---- 9 -----------------------------------------------------------------------------------------------------

def test_check9_passes_on_consistent_calls(db):
    hold(db, "BIG", 1000)
    call(db, "BIG", "sell", p=0.3, kind="holding", sell_kind="sell", broken="The auditor quit.")
    call(db, "NEW", "buy", size=20000)
    assert model.check_rule_guards(ctx_for(db)).status == "pass"


def test_check9_catches_a_sell_on_a_holding_under_5000(db):
    hold(db, "TINY", 20, price=100)
    call(db, "TINY", "sell", sell_kind="weak", kind="holding")
    r = model.check_rule_guards(ctx_for(db))
    assert r.status == "fail" and "TINY" in r.problems[0] and "under ₹5,000" in r.problems[0]


def test_check9_catches_a_sell_for_a_passive_fund_on_a_low_chance(db):
    hold(db, "NIFTYBEES", 1000)
    call(db, "NIFTYBEES", "sell", p=0.3, sell_kind="weak", kind="holding")
    r = model.check_rule_guards(ctx_for(db, rules=__import__("stockpilot.calls.decide", fromlist=["Rules"]).Rules(passive=("NIFTYBEES",))))
    assert r.status == "fail" and "passive fund" in " ".join(r.problems)


def test_check9_catches_a_sell_for_one_weak_quarter_alone(db):
    hold(db, "JIOFIN", 1000, price=100)
    call(db, "JIOFIN", "sell", p=0.45, kind="holding", sell_kind="sell", broken=None, stop=50, summary="One weak quarter.")
    r = model.check_rule_guards(ctx_for(db))
    assert r.status == "fail" and "JIOFIN" in r.problems[0] and "weak quarter" in r.problems[0]


def test_check9_catches_buys_over_budget(db):
    call(db, "AAA", "buy", size=70000)
    call(db, "BBB", "buy", size=60000)
    r = model.check_rule_guards(ctx_for(db, budget_default=100000.0))
    assert r.status == "fail" and "more than the ₹100,000 left" in " ".join(r.problems)


def test_check9_catches_numbers_that_contradict_each_other(db):
    call(db, "AAA", "buy", entry=100, stop=110, target=120)        # a stop above the price
    call(db, "BBB", "follow", entry=100, stop=90, target=80)       # a target below the stop
    call(db, "CCC", "buy", entry=100, stop=90, target=95)          # a Buy whose target is under its price
    text = " ".join(model.check_rule_guards(ctx_for(db)).problems)
    assert "AAA: its stop 110" in text and "BBB: its target 80" in text and "CCC: a Buy whose target 95" in text


# ---- 10 ----------------------------------------------------------------------------------------------------

def _brief(tmp_path, stocks):
    folder = tmp_path / "briefs"
    folder.mkdir()
    (folder / f"{DAY}.json").write_text(json.dumps({"as_of": str(DAY), "market": {"nifty": 25350}, "stocks": stocks}))
    return folder


ENTRY = {"symbol": "AAA", "price": {"close": 270.0, "ret_3m": 0.27, "vol_vs_20d": 2.9}, "fundamentals": {"profit_cagr_3y": 0.37},
         "headlines": [{"title": "Shriram Finance up 4% on Sensex entry"}]}


def test_check10_passes_when_cited_numbers_are_in_the_brief(db, tmp_path):
    call(db, "AAA", "buy", summary="Up 27% in three months, 2.9x its usual volume, now at ₹270.", moved=[{"reason": "profit growth of 37%", "points": 4}])
    r = model.check_analyst_numbers(ctx_for(db, briefs=_brief(tmp_path, [ENTRY])))
    assert r.status == "pass", r.problems
    assert r.numbers["spot_checked"] >= 3


def test_check10_catches_a_number_that_is_not_in_the_brief(db, tmp_path):
    call(db, "AAA", "buy", summary="Profit up 83% and the price is ₹412.", moved=[{"reason": "sales jumped 61%", "points": 4}])
    r = model.check_analyst_numbers(ctx_for(db, briefs=_brief(tmp_path, [ENTRY])))
    text = " ".join(r.problems)
    assert r.status == "fail" and "AAA" in text and "83%" in text


def test_check10_catches_an_answer_with_no_cited_evidence(db, tmp_path):
    call(db, "AAA", "buy", p=0.7, base=0.5, summary="Looks good.", moved=[], news=[])
    r = model.check_analyst_numbers(ctx_for(db, briefs=_brief(tmp_path, [ENTRY])))
    assert r.status == "fail" and "no evidence cited" in " ".join(r.problems)


def test_check10_fails_when_the_brief_was_not_kept(db, tmp_path):
    call(db, "AAA", "buy")
    r = model.check_analyst_numbers(ctx_for(db, briefs=tmp_path / "nowhere"))
    assert r.status == "fail" and "was not kept" in r.problems[0]


# ---- 11 ----------------------------------------------------------------------------------------------------

def _two_days(db, before, after):
    prev = DAY - timedelta(days=1)
    for s, sec in before.items():
        call(db, s, sec, made=prev)
    for s, sec in after.items():
        call(db, s, sec, made=DAY)


def test_check11_passes_when_sells_hold_steady(db):
    both = {f"S{i}": "sell" for i in range(6)}
    _two_days(db, both, both)
    assert model.check_regression(ctx_for(db)).status == "pass"


def test_check11_soft_fails_when_over_40_percent_of_sells_flip(db):
    before = {f"S{i}": "sell" for i in range(6)}
    after = {**{f"S{i}": "hold" for i in range(4)}, "S4": "sell", "S5": "sell"}
    _two_days(db, before, after)
    r = model.check_regression(ctx_for(db))
    assert r.status == "fail" and not r.blocks and r.numbers["flipped"] == 4 and "S0" in r.problems[0]


def test_check11_ignores_a_stock_that_was_not_called_the_day_before(db):
    _two_days(db, {f"S{i}": "sell" for i in range(5)}, {**{f"S{i}": "sell" for i in range(5)}, "NEW1": "sell", "NEW2": "sell"})
    assert model.check_regression(ctx_for(db)).status == "pass"


def test_check10_judges_the_models_own_chance_not_the_calibrated_one(db, tmp_path):
    """Calibration may move the stored chance away from the base rate; only the model's move needs cited evidence."""
    call(db, "AAA", "buy", p=0.62, base=0.5, summary="Looks good.", moved=[], news=[])
    db.execute("update calls set raw_probability = 0.5 where symbol = 'AAA'")
    r = model.check_analyst_numbers(ctx_for(db, briefs=_brief(tmp_path, [ENTRY])))
    assert "no evidence cited" not in " ".join(r.problems)
