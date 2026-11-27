"""Surcharge on the new regime (tax-rules.md section 7): 10% over Rs 50 lakh, 15% over 1 cr, 25% over 2 cr; capped at 15%
on dividends and s.196/197/198 gains; marginal relief at each threshold. Figures below are worked by hand."""
import pytest

from stockpilot.analysis import tax

R = tax.rules_for(2026)
LAKH, CR = 100_000, 10_000_000


def test_no_surcharge_at_exactly_fifty_lakh():
    out = tax.income_tax(slab_income=50 * LAKH, rules=R)
    assert out["surcharge"] == 0 and out["slab_tax"] == 1_080_000


def test_marginal_relief_just_over_fifty_lakh():
    # slab tax on 51 lakh = 1,110,000; on 50 lakh = 1,080,000. 10% surcharge = 111,000 would leave 1,221,000,
    # but tax plus surcharge may not exceed 1,080,000 + the Rs 1 lakh earned above the threshold = 1,180,000.
    out = tax.income_tax(slab_income=51 * LAKH, rules=R)
    assert out["slab_tax"] == 1_110_000
    assert out["surcharge"] == pytest.approx(70_000)
    assert out["total"] == pytest.approx(1_180_000 * 1.04)


def test_full_surcharge_once_relief_no_longer_bites():
    out = tax.income_tax(slab_income=120 * LAKH * 10 // 10, rules=R)      # Rs 1.2 crore
    assert out["slab_tax"] == 3_180_000
    assert out["surcharge"] == pytest.approx(477_000)                     # 15%


def test_marginal_relief_just_over_one_crore():
    # slab tax on 1.01 cr = 2,610,000. Tax at 1 cr with its 10% surcharge = 2,580,000 x 1.1 = 2,838,000, plus Rs 1 lakh = 2,938,000.
    out = tax.income_tax(slab_income=1 * CR + LAKH, rules=R)
    assert out["surcharge"] == pytest.approx(328_000)


def test_gains_surcharge_is_capped_at_fifteen_percent():
    # Rs 3 crore of s.197 gain: tax 3,750,000. The rate for 3 crore would be 25%; the cap makes it 15% = 562,500.
    out = tax.income_tax(ltcg_other=3 * CR, rules=R)
    assert out["ltcg_other"] == 3_750_000
    assert out["surcharge"] == pytest.approx(562_500)


def test_gains_over_one_crore_pay_ten_or_fifteen_not_twenty_five():
    out = tax.income_tax(ltcg_other=15 * CR // 10 * 4, rules=R)           # Rs 6 crore
    assert out["surcharge"] == pytest.approx(out["ltcg_other"] * 0.15)


def test_dividend_surcharge_is_capped_but_salary_pays_full_rate():
    # 1 cr salary + 1.5 cr dividend = 2.5 cr. Slab tax 7,080,000, of which 2,580,000 is on the salary alone.
    out = tax.income_tax(slab_income=1 * CR, dividend=15 * CR // 10, rules=R)
    assert out["slab_tax"] == 7_080_000
    assert out["surcharge"] == pytest.approx(2_580_000 * 0.25 + 4_500_000 * 0.15)


def test_below_the_threshold_nothing_changes_and_the_old_warning_is_gone():
    out = tax.income_tax(slab_income=6_000_000, rules=R)
    assert out["surcharge"] > 0 and not out["warnings"]
    assert tax.income_tax(slab_income=1_250_000, rules=R)["surcharge"] == 0
