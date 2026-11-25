"""Code decides: sections, sizes, the sector rules and the budget line. The model's probabilities come in; actions go out."""
from datetime import date

import pytest

from stockpilot import costs

from stockpilot.calls import decide
from stockpilot.calls.decide import Rules

TODAY = date(2026, 11, 20)
RULES = Rules()
PV = 1_000_000


def item(symbol, p, *, held=0, entry=100.0, stop=95.0, target=115.0, industry="Banks", adv_cr=80.0, lots=None,
         stop_hit=False, previous=None, buy_since=None, would="", price=None, **extra):
    base = {"symbol": symbol, "name": symbol.title(), "industry": industry, "probability": p, "base_rate": 0.5,
            "base_rate_n": 800, "kind": "holding" if held else "candidate", "held_qty": held, "price": price or entry,
            "levels": {"entry": entry, "stop": stop, "target": target, "why": "why"} if entry else None,
            "adv_cr": adv_cr, "hurdle": 0.014, "lots": lots or [], "stop_hit": stop_hit, "buy_since": buy_since,
            "summary": f"{symbol} summary.", "summary_bn": "সারাংশ", "moved_by": [], "risks": [], "news_used": [],
            "level_flag": None, "change_reason": None, "would_buy_if": would}
    base.update(extra)
    return base


def run(items, **kw):
    args = dict(rules=RULES, day=TODAY, portfolio_value=PV, sector_values={}, block_buys=None, not_now=[],
                setasides={}, recent_sector_buys={})
    args.update(kw)
    return decide.sections(items, **args)


def by(result):
    return {c["symbol"]: c for c in result["calls"]}


def lot(qty, acquired, cost=100.0, turns=None):
    return {"acquired_on": acquired, "quantity": qty, "cost": cost, "turns_long_term_on": turns}


def test_the_rules_default_to_the_owners_numbers():
    r = Rules()
    assert (r.buy_at, r.sell_at, r.max_single, r.risk_per_trade, r.follow_count, r.setaside_limit) == \
           (0.57, 0.40, 0.08, 0.01, 10, 3)


def test_every_stock_at_or_above_the_buy_line_is_a_buy_with_no_cap_on_the_count():
    items = [item(f"S{i}", 0.57 + i / 1000) for i in range(15)] + [item("LOW", 0.56)]
    calls = run(items)["calls"]
    buys = [c for c in calls if c["section"] == "buy"]
    assert len(buys) == 15 and by(run(items))["LOW"]["section"] == "follow"


def test_buys_come_best_expected_gain_first():
    items = [item("SMALL", 0.58, target=106), item("BIG", 0.70, target=130), item("MID", 0.62, target=115)]
    order = [c["symbol"] for c in run(items)["calls"] if c["section"] == "buy"]
    assert order == ["BIG", "MID", "SMALL"]


def test_size_is_the_smaller_of_the_cap_and_the_one_percent_risk_size_and_ignores_the_budget():
    # PV ₹10 lakh. Cap 8% = ₹80,000 = 800 shares at ₹100. Risk 1% = ₹10,000.
    near = by(run([item("NEAR", 0.7, stop=95)]))["NEAR"]        # risk size 10,000 / 5 = 2,000 → the cap wins
    far = by(run([item("FAR", 0.7, stop=70)]))["FAR"]           # risk size 10,000 / 30 = 333 → the risk wins
    assert (near["quantity"], near["sized_by"]) == (800, "cap")
    assert (far["quantity"], far["sized_by"]) == (333, "risk")
    assert near["amount"] == 80_000
    assert "budget" not in decide.sections.__code__.co_varnames


def test_expected_gain_is_quantity_times_the_edge_less_costs_and_tax():
    c = by(run([item("X", 0.65, stop=95, target=115)]))["X"]
    want = costs.expected_gain(800, 100, 95, 115, 0.65, 80.0)["net"]
    assert c["expected_gain_inr"] == pytest.approx(want, abs=1)


def test_a_holding_at_or_below_the_sell_line_is_sold_in_full_with_its_tax():
    lots = [lot(100, date(2026, 6, 1), cost=100), lot(100, date(2025, 1, 1), cost=100, turns=date(2026, 1, 2))]
    c = by(run([item("OLD", 0.38, held=200, entry=200, stop=190, target=230, lots=lots)]))["OLD"]
    assert (c["section"], c["quantity"], c["action"]) == ("sell", 200, "sell")
    assert "about ₹" in c["tax_line"] and "tax" in c["tax_line"]


def test_the_tax_line_says_when_a_lot_turns_long_term():
    lots = [lot(100, date(2025, 12, 1), cost=100, turns=date(2026, 12, 2))]
    c = by(run([item("WAIT", 0.35, held=100, entry=200, lots=lots)]))["WAIT"]
    assert "100 shares turn long-term on 2 Dec 2026 (12 days)" in c["tax_line"]
    assert "12.5%" in c["tax_line"]


def test_a_stop_reached_on_a_position_opened_from_a_call_is_a_sell_even_at_a_middling_probability():
    c = by(run([item("NEW", 0.52, held=500, entry=100, stop=95, stop_hit=True, price=94)]))["NEW"]
    assert c["section"] == "sell" and "stop" in c["why_code"].lower()


def test_old_holdings_never_get_a_stop():
    c = by(run([item("OLD", 0.50, held=50, entry=100, stop=95, stop_hit=False, price=60)]))["OLD"]   # far under any stop
    assert c["section"] == "hold"


def test_a_holding_above_eight_percent_is_trimmed_to_the_cap():
    # 1,000 shares at ₹100 = ₹1 lakh = 10% of ₹10 lakh; the cap is 800 shares.
    lots = [lot(1000, date(2024, 1, 1), cost=50, turns=date(2025, 1, 2))]
    c = by(run([item("BIG", 0.55, held=1000, lots=lots)]))["BIG"]
    assert (c["section"], c["quantity"]) == ("trim", 200)


def test_a_holding_at_the_buy_line_with_room_is_an_add_and_without_room_a_hold():
    room = by(run([item("ROOM", 0.7, held=300)]))["ROOM"]          # holds ₹30,000; cap ₹80,000 → room for 500
    assert (room["section"], room["action"], room["quantity"]) == ("buy", "add", 500)
    full = by(run([item("FULL", 0.7, held=800)]))["FULL"]
    assert full["section"] == "hold" and full["quantity"] == 0


def test_the_next_ten_below_the_line_are_followed_best_first_and_the_rest_are_only_logged():
    items = [item(f"F{i}", 0.56 - i / 100) for i in range(14)]
    calls = by(run(items))
    follow = [s for s in calls if calls[s]["section"] == "follow"]
    assert len(follow) == 10 and follow == [f"F{i}" for i in range(10)]
    assert calls["F12"]["section"] == "watch"


def test_followed_stocks_carry_what_would_make_them_a_buy():
    c = by(run([item("F", 0.5, would="Buy if it closes above ₹120 on volume.")]))["F"]
    assert c["section"] == "follow" and c["would_buy_if"] == "Buy if it closes above ₹120 on volume."


def test_holdings_not_sold_or_trimmed_are_hold():
    c = by(run([item("H", 0.50, held=10)]))["H"]
    assert c["section"] == "hold"


def test_not_now_for_buy_hides_a_stock_from_buys_and_follows_for_its_time():
    items = [item("A", 0.7), item("B", 0.5), item("C", 0.7)]
    calls = by(run(items, not_now=[("A", "buy"), ("B", "any")]))
    assert calls["A"]["section"] == "watch" and calls["B"]["section"] == "watch" and calls["C"]["section"] == "buy"


def test_not_now_for_sell_turns_a_sell_into_a_hold_and_buy_scope_leaves_sells_alone():
    items = [item("A", 0.3, held=100), item("B", 0.3, held=100)]
    calls = by(run(items, not_now=[("A", "sell"), ("B", "buy")]))
    assert calls["A"]["section"] == "hold" and calls["B"]["section"] == "sell"


def test_a_sector_with_three_set_asides_gets_at_most_one_buy_and_says_so():
    items = [item("B1", 0.72, target=130), item("B2", 0.66), item("B3", 0.60), item("T1", 0.65, industry="IT")]
    r = run(items, setasides={"Banks": 3})
    calls = by(r)
    assert [s for s in ("B1", "B2", "B3") if calls[s]["section"] == "buy"] == ["B1"]
    assert calls["B2"]["section"] == "follow" and "Banks" in " ".join(calls["B2"]["warnings"])
    assert calls["T1"]["section"] == "buy"
    assert any("Banks" in n and "3" in n and "week" in n for n in r["sector_notes"])


def test_a_sector_buy_in_the_last_week_leaves_no_room_for_a_different_stock():
    items = [item("B1", 0.72), item("B2", 0.66)]
    calls = by(run(items, setasides={"Banks": 3}, recent_sector_buys={"Banks": {"B2"}}))
    assert calls["B2"]["section"] == "buy" and calls["B1"]["section"] == "follow"


def test_a_buy_that_lifts_a_sector_share_gets_one_warning_line():
    # banks are ₹2.8 lakh of ₹10 lakh (28%); an ₹80,000 buy makes it 36%
    c = by(run([item("NEW", 0.7)], sector_values={"Banks": 280_000}))["NEW"]
    assert any("28% in Banks; this makes it 36%" in w for w in c["warnings"])
    small = by(run([item("NEW", 0.7)], sector_values={"Banks": 10_000}))["NEW"]
    assert not any("this makes it" in w for w in small["warnings"])      # below the 20% warning share


def test_a_repeat_buy_shows_the_first_day_of_its_run():
    c = by(run([item("AGAIN", 0.7, buy_since=date(2026, 11, 17))]))["AGAIN"]
    assert c["since"] == "2026-11-17" and "a buy since 17 Nov" in c["since_text"]


def test_blocked_buys_become_follows_with_the_reason():
    r = run([item("A", 0.7), item("B", 0.4, held=100)], block_buys="No prices loaded for 2026-11-20, so no buy calls tonight.")
    calls = by(r)
    assert calls["A"]["section"] == "follow" and "No prices" in " ".join(calls["A"]["warnings"])
    assert calls["B"]["section"] == "sell"                               # sells are never blocked


def test_a_stock_with_no_levels_or_no_portfolio_cannot_be_sized_so_it_is_followed():
    assert by(run([item("NOLEVEL", 0.7, entry=None)]))["NOLEVEL"]["section"] == "follow"
    assert by(run([item("NOPORT", 0.7)], portfolio_value=0))["NOPORT"]["section"] == "follow"


def test_borderline_is_within_five_points_of_either_line():
    its = [item("A", 0.54), item("B", 0.43), item("C", 0.50), item("D", 0.62)]
    assert decide.borderline(its, RULES) == ["A", "B", "D"]


@pytest.mark.parametrize("left,amounts,line", [
    (100_000, [40_000, 40_000, 40_000], "₹1 lakh left covers the first 2"),
    (150_000, [40_000, 40_000, 40_000], "₹1.5 lakh left covers the first 3"),
    (30_000, [40_000], "₹30,000 left does not cover the first buy"),
])
def test_budget_line(left, amounts, line):
    assert decide.budget_line(left, amounts) == line


def test_no_buys_no_budget_line():
    assert decide.budget_line(100_000, []) is None


def test_an_index_or_gold_etf_is_never_sold_for_failing_to_beat_the_nifty():
    # Found 2026-11-23: NIFTYBEES got "sell, chance 12%". A fund that tracks the index cannot beat it by the hurdle.
    r = by(run([item("NIFTYBEES", 0.12, held=100, passive=True, thesis_break=["30 points behind its sector over 3 months"]),
                item("RELIANCE", 0.12, held=100)]))
    assert r["NIFTYBEES"]["section"] == "hold"
    assert r["RELIANCE"]["section"] == "sell"


def test_a_passive_fund_is_still_trimmed_when_it_is_too_large():
    r = by(run([item("GOLDCASE", 0.12, held=1000, price=500.0, entry=500.0, stop=450.0, target=600.0, passive=True)]))
    assert r["GOLDCASE"]["section"] == "trim"


def test_rules_know_the_passive_funds_by_config_and_by_name():
    rules = Rules.from_config({"rules": {"passive": ["GOLDCASE"]}})
    assert rules.is_passive("GOLDCASE") and rules.is_passive("NIFTYBEES") and rules.is_passive("MON100ETF")
    assert not rules.is_passive("RELIANCE")
