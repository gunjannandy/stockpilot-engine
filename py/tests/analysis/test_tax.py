"""Tax maths, checked against the worked cases in docs/research/tax-rules.md (section numbers there)."""
from datetime import date

import pytest

from stockpilot.analysis import tax

RULES = tax.rules_for(2026)


# --- section 7: slabs, standard deduction, rebate ---------------------------------------------

def test_slab_tax_on_twelve_lakh_is_sixty_thousand_and_the_rebate_wipes_it():
    assert tax.slab_tax(1_200_000, RULES) == 60_000
    assert tax.income_tax(slab_income=1_200_000, rules=RULES)["total"] == 0


def test_a_salary_of_12_75_lakh_pays_nothing_after_the_standard_deduction():
    taxable = 1_275_000 - RULES.standard_deduction
    assert tax.income_tax(slab_income=taxable, rules=RULES)["total"] == 0


def test_just_above_twelve_lakh_marginal_relief_caps_tax_at_the_excess():
    out = tax.income_tax(slab_income=1_250_000, rules=RULES)
    assert out["slab_tax"] == 50_000                       # slab gives 67,500; relief caps it at 50,000
    assert out["total"] == pytest.approx(50_000 * 1.04)    # plus 4% cess


def test_rebate_never_shelters_special_rate_gains():
    out = tax.income_tax(slab_income=0, stcg_equity=100_000, rules=RULES)
    assert out["stcg_equity"] == 20_000 and out["total"] == pytest.approx(20_000 * 1.04)


# --- section 2: equity gains ------------------------------------------------------------------

def test_ltcg_equity_is_taxed_only_above_the_1_25_lakh_exemption():
    out = tax.income_tax(ltcg_equity=200_000, rules=RULES)
    assert out["ltcg_equity"] == pytest.approx(9_375)


def test_ltcg_equity_under_the_exemption_is_free():
    assert tax.income_tax(ltcg_equity=120_000, rules=RULES)["total"] == 0


@pytest.mark.parametrize("sold, term", [(date(2026, 1, 10), "short"), (date(2026, 1, 11), "long")])
def test_equity_is_long_term_only_after_more_than_12_months(sold, term):
    assert tax.term("equity", date(2025, 1, 10), sold) == term


@pytest.mark.parametrize("sold, term", [(date(2027, 1, 10), "short"), (date(2027, 1, 11), "long")])
def test_foreign_shares_need_more_than_24_months(sold, term):
    assert tax.term("foreign", date(2025, 1, 10), sold) == term


# --- section 3: which bucket a fund falls in ----------------------------------------------------

@pytest.mark.parametrize("category, bought, bucket", [
    ("Equity Scheme - Flexi Cap Fund", date(2020, 1, 1), "equity"),
    ("Hybrid Scheme - Arbitrage Fund", date(2024, 1, 1), "equity"),
    ("Debt Scheme - Liquid Fund", date(2024, 6, 1), "specified_mf"),
    ("Debt Scheme - Liquid Fund", date(2022, 6, 1), "other"),
    ("Other Scheme - FoF Overseas", date(2024, 1, 1), "other"),
    ("Hybrid Scheme - Balanced Hybrid Fund", date(2024, 1, 1), "other"),
])
def test_fund_bucket_follows_its_category_and_purchase_date(category, bought, bucket):
    assert tax.mf_bucket(category, bought) == bucket


def test_specified_mf_gains_are_always_short_term():
    assert tax.term("specified_mf", date(2020, 1, 1), date(2026, 6, 1)) == "short"


# --- section 2: grandfathering ---------------------------------------------------------------

@pytest.mark.parametrize("sale, gain", [(120, 0), (200, 50), (90, -10)])
def test_grandfathered_cost_is_higher_of_cost_and_lower_of_fmv_and_sale(sale, gain):
    cost = tax.grandfathered_cost(actual=100, fmv_2018=150, sale=sale)
    assert sale - cost == gain


# --- FIFO ---------------------------------------------------------------------------------------

def _lot(day, qty, cost, **kw):
    return {"id": kw.pop("id", 1), "kind": "equity", "symbol": "ABC", "isin": "INE000A01010",
            "acquired_on": day, "quantity": qty, "cost_per_unit": cost, "currency": "INR", **kw}


def _sale(day, qty, price, **kw):
    return {"kind": "equity", "symbol": "ABC", "isin": "INE000A01010", "sold_on": day,
            "quantity": qty, "price_per_unit": price, "currency": "INR", "expenses": 0.0, **kw}


def test_sales_eat_the_oldest_lot_first_and_split_across_lots():
    lots = [_lot(date(2025, 12, 1), 10, 120, id=2), _lot(date(2025, 1, 1), 10, 100, id=1)]
    rows = tax.realise(lots, [_sale(date(2026, 6, 1), 15, 150)])
    assert [(r["lot_id"], r["quantity"]) for r in rows] == [(1, 10), (2, 5)]
    assert [r["gain"] for r in rows] == [500, 150]
    assert {r["term"] for r in rows} == {"long", "short"}


def test_one_isin_never_matches_another_isins_lots():
    lots = [_lot(date(2025, 1, 1), 10, 100, isin="INE000B01010")]
    with pytest.raises(tax.OversoldError):
        tax.realise(lots, [_sale(date(2026, 6, 1), 5, 150)])


def test_expenses_reduce_the_gain_pro_rata():
    lots = [_lot(date(2025, 1, 1), 10, 100)]
    rows = tax.realise(lots, [_sale(date(2026, 6, 1), 10, 150, expenses=50)])
    assert rows[0]["gain"] == 450


def test_pre_2018_equity_lot_uses_the_31_jan_2018_value():
    lots = [_lot(date(2016, 1, 1), 10, 100)]
    rows = tax.realise(lots, [_sale(date(2026, 6, 1), 10, 200)], fmv_2018={"INE000A01010": 150})
    assert rows[0]["cost"] == 1500 and rows[0]["gain"] == 500 and rows[0]["grandfathered"]


def test_foreign_lot_gain_is_worked_in_rupees_at_each_dates_rate():
    lot = _lot(date(2024, 1, 15), 4, 100, kind="rsu", currency="USD", isin="US81762P1021", symbol="NOW")
    sale = _sale(date(2026, 6, 10), 4, 150, kind="rsu", currency="USD", isin="US81762P1021", symbol="NOW")
    rate = {date(2023, 12, 31): 83.0, date(2026, 5, 31): 90.0}.get
    rows = tax.realise([lot], [sale], rate_on=lambda d: rate(d))
    assert rows[0]["cost"] == 4 * 100 * 83.0            # TTBR at month end before the vest
    assert rows[0]["proceeds"] == 4 * 150 * 90.0        # rate at month end before the sale
    assert rows[0]["term"] == "long" and rows[0]["bucket"] == "foreign"


# --- section 5: netting -----------------------------------------------------------------------

def _row(bucket, gain, term):
    return {"bucket": bucket, "gain": gain, "term": term}


def test_short_term_loss_cuts_short_term_gain_before_tax():
    net = tax.net_gains([_row("equity", 80_000, "short"), _row("equity", -50_000, "short")], rules=RULES)
    assert net["stcg_equity"] == 30_000


def test_long_term_loss_cannot_offset_short_term_gain():
    net = tax.net_gains([_row("equity", 100_000, "short"), _row("equity", -40_000, "long")], rules=RULES)
    assert net["stcg_equity"] == 100_000 and net["carry_forward"]["ltcl"] == 40_000


def test_short_term_loss_spills_into_long_term_gain():
    net = tax.net_gains([_row("equity", 150_000, "long"), _row("equity", -60_000, "short")], rules=RULES)
    assert net["ltcg_equity"] == 90_000 and net["carry_forward"]["stcl"] == 0
    assert tax.income_tax(**tax.inputs(net), rules=RULES)["total"] == 0     # under the exemption


def test_unused_loss_carries_forward_and_old_ones_expire_after_eight_years():
    carried = [{"year": 2017, "stcl": 10_000, "ltcl": 0}, {"year": 2020, "stcl": 5_000, "ltcl": 0}]
    net = tax.net_gains([_row("equity", 8_000, "short")], rules=RULES, tax_year=2026, carried=carried)
    assert net["stcg_equity"] == 3_000                   # 2017 loss is past 8 years; 2020's 5,000 applies
    assert net["carry_forward"]["stcl"] == 0


def test_other_fund_ltcg_is_taxed_at_12_5_without_an_exemption():
    net = tax.net_gains([_row("other", 100_000, "long")], rules=RULES)
    assert tax.income_tax(**tax.inputs(net), rules=RULES)["total"] == pytest.approx(12_500 * 1.04)


def test_slab_bucket_short_gains_join_the_slab_income():
    net = tax.net_gains([_row("specified_mf", 50_000, "short")], rules=RULES)
    assert tax.inputs(net)["slab_income"] == 50_000


def test_the_first_long_term_day_is_the_day_after_the_holding_period():
    from datetime import date as d
    assert tax.turns_long_term_on("equity", d(2023, 3, 1)) == d(2024, 3, 2)
    assert tax.turns_long_term_on("foreign", d(2022, 2, 28)) == d(2024, 2, 29)
    assert tax.turns_long_term_on("specified_mf", d(2024, 1, 1)) is None      # never long-term
    assert tax.term("equity", d(2023, 3, 1), tax.turns_long_term_on("equity", d(2023, 3, 1))) == "long"
    assert tax.term("equity", d(2023, 3, 1), d(2024, 3, 1)) == "short"
