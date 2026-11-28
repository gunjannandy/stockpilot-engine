"""C-048-1: the XBRL parse and the yfinance fallback, from fixtures."""
from datetime import date

from stockpilot.sources import facts as f
from stockpilot.sources import facts_sources as fs

XBRL = b"""<?xml version="1.0"?>
<xbrli:xbrl xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:in-bse-fin="http://x/in-bse-fin">
 <xbrli:context id="FY"><xbrli:period><xbrli:startDate>2025-04-01</xbrli:startDate><xbrli:endDate>2026-03-31</xbrli:endDate></xbrli:period></xbrli:context>
 <xbrli:context id="END"><xbrli:period><xbrli:instant>2026-03-31</xbrli:instant></xbrli:period></xbrli:context>
 <in-bse-fin:ScaleOfFigures contextRef="FY">Lakhs</in-bse-fin:ScaleOfFigures>
 <in-bse-fin:RevenueFromOperations contextRef="FY">1200000</in-bse-fin:RevenueFromOperations>
 <in-bse-fin:ProfitLossForPeriod contextRef="FY">150000</in-bse-fin:ProfitLossForPeriod>
 <in-bse-fin:Equity contextRef="END">2000000</in-bse-fin:Equity>
</xbrli:xbrl>"""


def test_xbrl_parse_gives_crore_figures_with_filing_source():
    by = {r.metric: r for r in fs.parse_xbrl(XBRL, date(2026, 3, 31), date(2026, 5, 22))}
    assert by["sales"].value == 12000.0 and by["profit"].value == 1500.0 and by["equity"].value == 20000.0
    assert all(r.source == "nse" for r in by.values())


def test_yfinance_fills_only_what_the_filing_lacks():
    filed = fs.parse_xbrl(XBRL, date(2026, 3, 31), date(2026, 5, 22))
    gap = fs.from_yfinance({"returnOnEquity": 0.99, "debtToEquity": 45.0}, date(2026, 11, 25))
    q = f.quality(filed + gap, date(2026, 11, 25))
    assert q["roe_pct"] == 7.5            # the filing's profit over equity wins over yfinance's 99
    assert q["debt_to_equity"] == 0.45    # no filing figure: yfinance fills the gap


def test_garbage_filing_gives_no_records_so_yfinance_stands_alone():
    assert fs.parse_xbrl(b"<html>blocked</html>", date(2026, 3, 31), date(2026, 5, 22)) == []
