"""Adapters: NSE XBRL results, shareholding and pledge rows, yfinance info -> Records with their available dates."""
import json
from datetime import date

from stockpilot.sources import facts as f
from stockpilot.sources import facts_sources as fs

XBRL = b"""<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-bse-fin="http://x/in-bse-fin">
 <xbrli:context id="FY"><xbrli:period><xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id="Q4"><xbrli:period><xbrli:startDate>2026-01-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id="END"><xbrli:period><xbrli:instant>2026-03-31</xbrli:instant></xbrli:period></xbrli:context>
 <in-bse-fin:ScaleOfFigures contextRef="FY">Lakhs</in-bse-fin:ScaleOfFigures>
 <in-bse-fin:RevenueFromOperations contextRef="FY">1200000</in-bse-fin:RevenueFromOperations>
 <in-bse-fin:RevenueFromOperations contextRef="Q4">300000</in-bse-fin:RevenueFromOperations>
 <in-bse-fin:ProfitLossForPeriod contextRef="FY">150000</in-bse-fin:ProfitLossForPeriod>
 <in-bse-fin:Equity contextRef="END">2000000</in-bse-fin:Equity>
 <in-bse-fin:Borrowings contextRef="END">500000</in-bse-fin:Borrowings>
</xbrli:xbrl>"""


def test_xbrl_takes_full_year_not_quarter_and_converts_lakhs_to_crore():
    recs = fs.parse_xbrl(XBRL, period_end=date(2026, 3, 31), available_on=date(2026, 5, 22))
    by = {r.metric: r for r in recs}
    assert by["sales"].value == 12000.0          # 1,200,000 lakh = 12,000 crore, the year not the quarter
    assert by["profit"].value == 1500.0 and by["equity"].value == 20000.0 and by["debt"].value == 5000.0
    assert all(r.available_on == date(2026, 5, 22) and r.source == "nse" for r in recs)


def test_xbrl_garbage_gives_no_records():
    assert fs.parse_xbrl(b"<html>blocked</html>", date(2026, 3, 31), date(2026, 5, 22)) == []


def test_shareholding_rows_become_dated_records():
    rows = [{"date": "30-SEP-2026", "pr_and_prgrp": "55.12", "submissionDate": "18-OCT-2026"},
            {"date": "30-JUN-2026", "pr_and_prgrp": "-", "submissionDate": "15-JUL-2026"}]
    recs = fs.parse_shareholding(rows)
    assert [(r.metric, r.value, r.period_end, r.available_on) for r in recs] == \
        [("promoter_pct", 55.12, date(2026, 9, 30), date(2026, 10, 18))]


def test_pledge_rows_become_dated_records():
    rows = [{"date": "30-SEP-2026", "percSharesPledged": "1.5", "broadcastDate": "18-OCT-2026 10:00:00"}]
    (r,) = fs.parse_pledge(rows)
    assert (r.metric, r.value, r.available_on) == ("pledge_pct", 1.5, date(2026, 10, 18))


def test_yfinance_info_is_dated_the_day_we_fetched_it():
    info = {"trailingPE": 20.5, "priceToBook": 3.0, "returnOnEquity": 0.18, "debtToEquity": 45.0,
            "marketCap": 5.2e10, "dividendYield": 1.1, "heldPercentInsiders": 0.55, "junk": None}
    recs = {r.metric: r for r in fs.from_yfinance(info, fetched_on=date(2026, 11, 25))}
    assert recs["roe_pct"].value == 18.0 and recs["debt_to_equity"].value == 0.45
    assert recs["market_cap_cr"].value == 5200.0 and recs["pe"].value == 20.5
    assert all(r.available_on == date(2026, 11, 25) and r.source == "yfinance" for r in recs.values())


def test_run_builds_files_reports_coverage_and_survives_a_bad_symbol(tmp_path):
    def gather(sym):
        if sym == "BAD":
            raise OSError("blocked")
        return [f.Record("promoter_pct", 50.0, date(2026, 9, 30), date(2026, 10, 18), "nse")]
    universe = [{"symbol": "AAA", "exchange": "NSE", "name": "A", "sector": "S"},
                {"symbol": "BAD", "exchange": "NSE", "name": "B", "sector": "S"}]
    cov = fs.run(universe, gather, prices={"AAA": 100.0}, out=tmp_path, today=date(2026, 11, 25))
    assert cov["universe"] == 2 and cov["with_facts"] == 1 and cov["failed"] == ["BAD"]
    doc = json.loads((tmp_path / "stock" / "AAA.json").read_text())
    assert doc["quality"]["promoter_pct"] == 50.0
    assert not (tmp_path / "stock" / "BAD.json").exists()
    assert json.loads((tmp_path / "facts-coverage.json").read_text())["universe"] == 2
