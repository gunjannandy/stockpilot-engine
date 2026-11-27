"""Lane E, stricter Sell (v10 decision 8). A holding is a Sell only for: its sell price reached (the code-set stop on a
position opened from a call), a reason for owning it the analyst says has broken, or the size limit. A low chance alone is
Weak. A holding under ₹5,000 never gets a Sell. A holding marked "I hold this for years" is Review, never Sell, for one
weak quarter. Code facts such as a one-quarter profit dip go to the analyst; they no longer sell by themselves."""
from datetime import date

from test_decide import item, lot, run, by

OLD = [lot(100, date(2025, 1, 1), cost=100, turns=date(2026, 1, 2))]


def held(symbol, p, **kw):
    kw.setdefault("held", 100)
    kw.setdefault("lots", OLD)
    return item(symbol, p, **kw)             # 100 shares at ₹100 = ₹10,000


def test_a_low_chance_alone_is_weak_not_sell():
    c = by(run([held("LOW", 0.35)]))["LOW"]
    assert (c["section"], c["sell_kind"]) == ("sell", "weak")
    assert "sell line" in c["why_code"] and c["quantity"] == 100


def test_a_broken_sell_price_is_a_sell_even_at_a_fine_chance():
    c = by(run([held("STOP", 0.55, stop_hit=95.0, price=94.0)]))["STOP"]
    assert (c["section"], c["sell_kind"]) == ("sell", "sell")
    assert "stop" in c["why_code"].lower()


def test_an_analyst_stated_broken_reason_is_a_sell_even_at_a_fine_chance():
    c = by(run([held("BAD", 0.55, broken_reason="the auditor resigned and the accounts are on hold")]))["BAD"]
    assert (c["section"], c["sell_kind"]) == ("sell", "sell")
    assert "auditor resigned" in c["why_code"] and "tax" in c["tax_line"]


def test_a_broken_reason_beside_a_low_chance_keeps_both_sentences():
    c = by(run([held("BOTH", 0.30, broken_reason="the promoter pledged most of his shares")]))["BOTH"]
    assert c["sell_kind"] == "sell" and "sell line" in c["why_code"] and "pledged" in c["why_code"]


def test_the_size_limit_is_a_sell_kind_trim():
    big = item("BIG", 0.55, held=1000, entry=100, price=100, lots=[lot(1000, date(2024, 1, 1))])
    c = by(run([big]))["BIG"]
    assert (c["section"], c["sell_kind"], c["quantity"]) == ("trim", "sell", 200)


def test_a_code_fact_alone_never_sells():
    """The old rule sold on an ASM flag, a lagging sector or one weak quarter. Now those are facts for the analyst."""
    c = by(run([held("JIOFIN", 0.50, thesis_break=["profit for the quarter to Sep 2026 fell 30% on a year earlier"])]))["JIOFIN"]
    assert (c["section"], c["sell_kind"]) == ("hold", None)


def test_a_jiofin_style_one_quarter_dip_beside_a_middling_chance_is_not_a_sell():
    c = by(run([held("JIOFIN", 0.44, thesis_break=["profit for the quarter to Sep 2026 fell 30% on a year earlier"])]))["JIOFIN"]
    assert c["section"] == "hold"


def test_a_jiofin_style_dip_with_a_low_chance_is_weak_never_sell():
    c = by(run([held("JIOFIN", 0.38, thesis_break=["profit for the quarter to Sep 2026 fell 30% on a year earlier"])]))["JIOFIN"]
    assert c["sell_kind"] == "weak"


def test_a_blank_broken_reason_is_no_reason():
    c = by(run([held("BLANK", 0.55, broken_reason="   ")]))["BLANK"]
    assert c["section"] == "hold"


def test_a_holding_under_5000_rupees_never_gets_a_sell():
    small = [held("TINY", 0.30, held=40, broken_reason="results fraud", stop_hit=95.0, price=94.0)]   # 40 x 94 = ₹3,760
    c = by(run(small))["TINY"]
    assert c["section"] == "hold" and c["sell_kind"] is None
    assert any("5,000" in w for w in c["warnings"])


def test_a_holding_at_exactly_5000_rupees_can_be_sold():
    c = by(run([held("EDGE", 0.30, held=50, price=100.0)]))["EDGE"]       # 50 x 100 = ₹5,000
    assert c["section"] == "sell"


def test_a_long_term_marked_holding_is_review_for_a_weak_quarter():
    c = by(run([held("KEEP", 0.35, long_term=True, thesis_break=["profit fell 30%"])]))["KEEP"]
    assert (c["section"], c["sell_kind"]) == ("sell", "review")
    assert "years" in c["why_code"]


def test_a_long_term_marked_holding_is_never_sell_even_with_a_broken_reason_or_a_stop():
    c = by(run([held("KEEP", 0.55, long_term=True, broken_reason="one weak quarter", stop_hit=95.0, price=94.0)]))["KEEP"]
    assert c["sell_kind"] == "review"


def test_a_long_term_marked_holding_with_a_fine_chance_is_a_plain_hold():
    assert by(run([held("KEEP", 0.55, long_term=True)]))["KEEP"]["section"] == "hold"


def test_a_marked_holding_over_the_size_limit_is_still_trimmed():
    big = item("BIG", 0.55, held=1000, entry=100, price=100, lots=[lot(1000, date(2024, 1, 1))], long_term=True)
    assert by(run([big]))["BIG"]["section"] == "trim"


def test_not_now_hides_weak_and_review_too():
    items = [held("A", 0.30), held("B", 0.30, long_term=True)]
    calls = by(run(items, not_now=[("A", "sell"), ("B", "sell")]))
    assert calls["A"]["section"] == calls["B"]["section"] == "hold"


def test_a_passive_fund_ignores_a_broken_reason():
    c = by(run([held("NIFTYBEES", 0.55, passive=True, broken_reason="tracking error")]))["NIFTYBEES"]
    assert c["section"] == "hold"


def test_every_call_carries_sell_kind_none_unless_sell_or_trim():
    r = by(run([item("B", 0.7), item("F", 0.5), held("H", 0.5)]))
    assert all(c["sell_kind"] is None for c in r.values())
