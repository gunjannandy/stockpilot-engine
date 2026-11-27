from datetime import date

from stockpilot import store
from stockpilot.trades import corporate_actions, lots, rsu


def vest(on, qty, status="confirmed"):
    return lots.Trade("fidelity", f"V{on}", "rsu", "NOW", "US81762P1021", "vest", on, qty, 140.0,
                      currency="USD", status=status)


def test_payslip_and_form16_numbers():
    slip = "Pay Period: November 2026\nBasic 250,000.00\nRSU Perquisite 1,85,000.00\nNet Pay 3,10,000.00"
    assert rsu.parse_payslip(slip) == ("2026-11", 185000.0)
    assert rsu.parse_payslip("Pay Period: October 2026\nBasic 250,000.00") == ("2026-10", 0.0)
    f16 = "Form 16 Part B  Assessment Year 2026-27\nValue of perquisites under section 17(2) 7,40,000.00"
    assert rsu.parse_form16(f16) == ("2025-26", 740000.0)


def test_quarterly_pattern_projects_expected_vests():
    confirmed = [vest(date(2026, 2, 15), 20), vest(date(2026, 5, 15), 20), vest(date(2026, 8, 15), 20)]
    out = rsu.expected_vests(confirmed, through=date(2027, 3, 1))
    assert [(t.trade_date, t.quantity, t.status, t.source) for t in out] == [
        (date(2026, 11, 15), 20.0, "expected", "rsu_inference"),
        (date(2027, 2, 15), 20.0, "expected", "rsu_inference")]


def test_confirmed_vest_replaces_the_expected_one():
    confirmed = [vest(date(2026, 8, 15), 20), vest(date(2026, 11, 16), 18)]
    out = rsu.expected_vests(confirmed, through=date(2027, 1, 1))
    assert out == []          # Nov vest is confirmed (a day late); next is Feb 2027
    assert rsu.expected_vests(confirmed, through=date(2027, 3, 1))[0].trade_date == date(2027, 2, 16)


def test_now_split_scales_projected_quantity():
    confirmed = [vest(date(2025, 8, 15), 20), vest(date(2025, 11, 15), 20)]
    split = corporate_actions.Action("NOW", "US81762P1021", date(2025, 12, 18), "split", 5, 1, "5-for-1")
    out = rsu.expected_vests(confirmed, through=date(2026, 3, 1), actions=[split])
    assert [(t.trade_date, t.quantity) for t in out] == [(date(2026, 2, 15), 100.0)]


def test_payslip_months_stand_in_when_no_vest_email(tmp_path):
    out = rsu.vests_from_payslips([("2026-02", 185000.0), ("2026-05", 190000.0), ("2026-04", 0.0)],
                                  price_inr=lambda month: 12000.0)
    assert [(t.trade_date.strftime("%Y-%m"), t.status) for t in out] == [("2026-02", "expected"), ("2026-05", "expected")]
    assert round(out[0].quantity) == 15            # 185000 / 12000
    assert all(t.price is None for t in out)


def test_expected_vests_never_reach_lots(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    c = [vest(date(2026, 8, 15), 20)]
    lots.save_trades(db, c + rsu.expected_vests(c, through=date(2027, 1, 1)))
    lots.rebuild(db)
    assert db.execute("select count(*) from lots").fetchone()[0] == 1
    assert db.execute("select count(*) from trades where status = 'expected'").fetchone()[0] == 1
