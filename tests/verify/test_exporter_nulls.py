"""Check 6 found insurers whose filings carry no net profit; the stock file must leave such a quarter out, not export null."""
from datetime import date

from stockpilot.site_export import stock


def test_a_quarter_with_no_profit_or_sales_is_left_out_not_exported_as_null():
    rows = [("LIFE", date(2026, 3, 31), 100e7, None), ("LIFE", date(2026, 6, 30), 110e7, None), ("LIFE", date(2026, 9, 30), None, 5e7),
            ("OK", date(2026, 9, 30), 120e7, 10e7)]
    quarters, years = stock._quarters([r for r in rows if r[0] == "LIFE"])
    assert quarters == [] and years == []
    quarters, _ = stock._quarters([r for r in rows if r[0] == "OK"])
    assert [q["period_end"] for q in quarters] == ["2026-09-30"] and quarters[0]["profit_cr"] == 10.0
