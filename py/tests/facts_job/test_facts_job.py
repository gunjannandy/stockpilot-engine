import json
import re
from datetime import date

from stockpilot.jobs import facts as job
from stockpilot.jobs.facts.templates import TEMPLATES, fields
from stockpilot.sources.facts import Record

DAY = date(2026, 11, 28)
BN = re.compile(r"[ঀ-৿]")


def recs(profit=1500.0, sales=12000.0):
    end, avail = date(2026, 3, 31), date(2026, 5, 22)
    old = date(2025, 3, 31)
    return [Record("sales", sales, end, avail, "nse"), Record("sales", sales / 1.1, old, date(2025, 5, 20), "nse"),
            Record("profit", profit, end, avail, "nse"), Record("equity", 10000.0, end, avail, "nse"),
            Record("debt", 1000.0, end, avail, "nse"), Record("shares", 100.0, end, avail, "nse"),
            Record("pe", 18.0, DAY, DAY, "yfinance")]


def universe(n):
    return [{"symbol": f"S{i}", "exchange": "NSE", "name": f"Stock {i}", "sector": "Sec"} for i in range(n)]


def test_row_has_sector_comparison_sentences_in_both_languages_and_figures_with_source():
    out = job.collect(universe(6), lambda s: recs(), {f"S{i}": 100.0 for i in range(6)}, DAY)
    r = out[0]
    assert r["id"] == "NSE:S0" and r["pe_sector"] == 6.7 and r["pe"] == 6.7 and r["roe_pct"] == 15.0
    sent = json.loads(r["sentences_json"])
    assert sent and all(BN.search(s["bn"]) and s["en"] for s in sent)
    figs = {f["metric"]: f for f in json.loads(r["figures_json"])}
    assert figs["sales"] == {"metric": "sales", "value": 12000.0, "period": "2026-03-31", "source": "nse"}
    assert figs["pe"]["source"] == "yfinance"


def test_a_failing_stock_is_left_out_and_the_run_goes_on():
    def gather(s):
        if s == "S1":
            raise OSError("blocked")
        return recs()
    out = job.collect(universe(3), gather, {}, DAY)
    assert [r["symbol"] for r in out] == ["S0", "S2"]


def test_price_sentences_from_history():
    rows = [{"close": 100 + (i % 7) * (-1) ** i, "volume": 1000 + i} for i in range(80)]
    keys = [s["key"] for s in job.price_sentences(rows)]
    assert keys == ["biggest_fall", "swings", "trading"]
    assert job.price_sentences(rows[:10]) == []


def test_every_template_has_bengali_with_the_same_placeholders():
    for key, t in TEMPLATES.items():
        assert BN.search(t["bn"]) and fields(t["en"]) == fields(t["bn"]), key


