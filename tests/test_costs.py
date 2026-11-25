"""Zerodha delivery charges, slippage by liquidity, and the hurdle a stock must clear over the Nifty."""
import pytest

from stockpilot import costs


def test_round_trip_charges_on_a_one_lakh_trade_match_a_hand_calculation():
    # ₹1,00,000 bought and sold. Buy: STT 100, stamp 15, exchange 2.97, SEBI 0.10, GST 18% of (2.97 + 0.10).
    # Sell: STT 100, exchange 2.97, SEBI 0.10, GST on those, DP 15.34. Brokerage 0.
    c = costs.charges(100_000, 100_000)
    gst = 0.18 * (2.97 + 0.10)
    assert c["buy"] == pytest.approx(100 + 15 + 2.97 + 0.10 + gst, abs=0.01)
    assert c["sell"] == pytest.approx(100 + 2.97 + 0.10 + gst + 15.34, abs=0.01)
    assert c["total"] == pytest.approx(c["buy"] + c["sell"])


def test_slippage_per_side_scales_with_liquidity():
    assert costs.slippage_rate(50) == pytest.approx(0.0005)
    assert costs.slippage_rate(400) == pytest.approx(0.0005)      # more liquid than the top end: no better
    assert costs.slippage_rate(1) == pytest.approx(0.003)
    assert costs.slippage_rate(0.2) == pytest.approx(0.003)       # thinner than the bottom end: no worse
    mid = costs.slippage_rate(7)
    assert 0.0005 < mid < 0.003


def test_round_trip_cost_in_rupees_and_percent_includes_slippage_both_ways():
    one_lakh = costs.round_trip(100_000, adv_cr=50)
    assert one_lakh["slippage"] == pytest.approx(2 * 0.0005 * 100_000)
    assert one_lakh["total"] == pytest.approx(one_lakh["charges"] + one_lakh["slippage"])
    assert one_lakh["pct"] == pytest.approx(one_lakh["total"] / 100_000)
    thin = costs.round_trip(100_000, adv_cr=1)
    assert thin["pct"] > one_lakh["pct"]


def test_hurdle_covers_costs_and_the_tax_on_the_gain():
    # Costs 0.6% round trip; the Nifty is assumed to give 3% over three months; 20% short-term tax.
    # A stock must reach g where g - 0.006 - 0.2 * (g - 0.006) = 0.03  →  g = 0.006 + 0.03 / 0.8 = 0.0435,
    # so it must beat the Nifty by 1.35 percentage points.
    assert costs.hurdle(round_trip_pct=0.006, nifty_3m=0.03, tax_rate=0.20) == pytest.approx(0.0135)


def test_hurdle_is_higher_for_a_thin_stock_than_a_liquid_one():
    liquid = costs.hurdle_for(100_000, adv_cr=80)
    thin = costs.hurdle_for(100_000, adv_cr=1.5)
    assert thin > liquid > 0.0


def test_expected_gain_after_costs_and_tax_on_a_worked_example():
    # 100 shares at ₹1,000 (₹1 lakh). Stop ₹950 (down 5%), target ₹1,150 (up 15%). p = 0.6, liquid stock.
    g = costs.expected_gain(quantity=100, entry=1000, stop=950, target=1150, p=0.6, adv_cr=80)
    gross = 100_000 * (0.6 * 0.15 - 0.4 * 0.05)                 # 7,000
    rt = costs.round_trip(100_000, adv_cr=80)["total"]
    tax = 0.6 * 0.20 * max(0.0, 100_000 * 0.15 - rt)            # tax is paid only when the target is reached
    assert g["gross"] == pytest.approx(gross)
    assert g["costs"] == pytest.approx(rt)
    assert g["tax"] == pytest.approx(tax)
    assert g["net"] == pytest.approx(gross - rt - tax)


def test_a_losing_bet_has_no_tax_and_a_negative_net():
    g = costs.expected_gain(quantity=100, entry=1000, stop=900, target=1020, p=0.3, adv_cr=80)
    assert g["tax"] == pytest.approx(0.3 * 0.20 * max(0, 100_000 * 0.02 - g["costs"]))
    assert g["net"] < 0


def test_tax_if_sold_today_uses_short_and_long_rates_by_lot():
    from datetime import date
    lots = [
        {"acquired_on": date(2026, 6, 1), "quantity": 10, "cost": 100.0, "turns_long_term_on": date(2027, 6, 2)},
        {"acquired_on": date(2025, 1, 1), "quantity": 10, "cost": 100.0, "turns_long_term_on": date(2026, 1, 2)},
        {"acquired_on": date(2025, 1, 1), "quantity": 10, "cost": 300.0, "turns_long_term_on": date(2026, 1, 2)},   # a loss
    ]
    t = costs.tax_if_sold(lots, price=200.0, on=date(2026, 11, 20))
    assert t["short_gain"] == pytest.approx(1000) and t["long_gain"] == pytest.approx(1000 - 1000)
    # the loss is set off against the long-term gain; only the short-term gain is taxed, at 20%
    assert t["tax"] == pytest.approx(0.20 * 1000)


def test_tax_if_sold_taxes_a_long_term_gain_at_12_5_percent():
    from datetime import date
    lots = [{"acquired_on": date(2025, 1, 1), "quantity": 10, "cost": 100.0, "turns_long_term_on": date(2026, 1, 2)}]
    t = costs.tax_if_sold(lots, price=200.0, on=date(2026, 11, 20))
    assert t["long_gain"] == pytest.approx(1000)
    assert t["tax"] == pytest.approx(0.125 * 1000)       # the yearly ₹1.25 lakh exemption is ignored: an upper bound
