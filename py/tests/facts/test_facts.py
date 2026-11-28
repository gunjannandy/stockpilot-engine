"""Per-stock facts: each value carries the date it became available; nothing is used before that date."""
import json
from datetime import date

from stockpilot.sources import facts as f

REC = f.Record


def recs():
    return [
        REC("sales", 100.0, period_end=date(2025, 3, 31), available_on=date(2025, 5, 20), source="nse"),
        REC("sales", 120.0, period_end=date(2026, 3, 31), available_on=date(2026, 5, 22), source="nse"),
        REC("profit", 10.0, period_end=date(2025, 3, 31), available_on=date(2025, 5, 20), source="nse"),
        REC("profit", 15.0, period_end=date(2026, 3, 31), available_on=date(2026, 5, 22), source="nse"),
        REC("promoter_pct", 55.0, period_end=date(2026, 9, 30), available_on=date(2026, 10, 18), source="nse"),
        REC("pledge_pct", 2.0, period_end=date(2026, 9, 30), available_on=date(2026, 10, 18), source="nse"),
    ]


def test_no_value_is_used_before_its_available_date():
    # FY26 ended 31 Mar 2026 but results came out 22 May: on 10 May only FY25 may be used
    seen = f.as_of(recs(), date(2026, 5, 10))
    assert [r.value for r in seen if r.metric == "sales"] == [100.0]
    assert not any(r.available_on > date(2026, 5, 10) for r in seen)


def test_growth_uses_only_what_was_known_on_the_day():
    early = f.quality(recs(), date(2026, 5, 10))
    late = f.quality(recs(), date(2026, 6, 1))
    assert early["sales_growth_yoy_pct"] is None          # one year only: cannot grow
    assert late["sales_growth_yoy_pct"] == 20.0
    assert late["profit_growth_yoy_pct"] == 50.0


def test_shareholding_is_latest_known_and_respects_date():
    assert f.quality(recs(), date(2026, 10, 1))["promoter_pct"] is None
    q = f.quality(recs(), date(2026, 10, 20))
    assert (q["promoter_pct"], q["pledge_pct"]) == (55.0, 2.0)


def test_roe_roce_debt_from_balance_records():
    r = recs() + [
        REC("equity", 200.0, date(2026, 3, 31), date(2026, 5, 22), "nse"),
        REC("debt", 50.0, date(2026, 3, 31), date(2026, 5, 22), "nse"),
        REC("capital_employed", 250.0, date(2026, 3, 31), date(2026, 5, 22), "nse"),
        REC("ebit", 40.0, date(2026, 3, 31), date(2026, 5, 22), "nse"),
    ]
    q = f.quality(r, date(2026, 6, 1))
    assert q["roe_pct"] == 7.5 and q["roce_pct"] == 16.0 and q["debt_to_equity"] == 0.25


def test_yfinance_fills_gaps_but_never_overrides_filings():
    nse = [REC("promoter_pct", 55.0, date(2026, 9, 30), date(2026, 10, 18), "nse")]
    yf = [REC("promoter_pct", 40.0, date(2026, 11, 1), date(2026, 11, 25), "yfinance"),
          REC("roe_pct", 12.0, date(2026, 11, 1), date(2026, 11, 25), "yfinance")]
    q = f.quality(nse + yf, date(2026, 11, 25))
    assert q["promoter_pct"] == 55.0 and q["roe_pct"] == 12.0


def test_valuation_pe_pb_from_price_and_filings():
    # figures in rupees crore; shares in crore
    r = recs() + [REC("equity", 200.0, date(2026, 3, 31), date(2026, 5, 22), "nse"),
                  REC("shares", 1.5, date(2026, 3, 31), date(2026, 5, 22), "nse")]
    v = f.valuation(r, date(2026, 6, 1), price=300.0)
    assert (v["pe"], v["pb"], v["market_cap_cr"]) == (30.0, 2.25, 450.0)


def test_valuation_before_latest_results_uses_older_year():
    r = recs() + [REC("shares", 1.5, date(2025, 3, 31), date(2025, 5, 20), "nse")]
    assert f.valuation(r, date(2026, 5, 10), price=300.0)["pe"] == 45.0     # FY25 profit 10 -> eps 6.67


def test_missing_inputs_are_none_and_listed_as_not_available():
    facts = f.build_facts("FIXA", "NSE", "Fixture Alpha Ltd", "Fixture sector", [], date(2026, 6, 1), price=None)
    assert facts["valuation"]["pe"] is None
    assert {"pe", "roe_pct", "promoter_pct"} <= set(facts["not_available"])


def test_build_facts_shape_has_sentences_in_both_languages():
    facts = f.build_facts("FIXA", "NSE", "Fixture Alpha Ltd", "Fixture sector", recs(), date(2026, 10, 20), price=300.0)
    assert facts["as_of"] == "2026-10-20"
    for s in facts["sentences"]:
        assert s["en"] and s["bn"] and s["key"]
    json.dumps(facts)


def test_ten_year_history_not_available_when_short():
    facts = f.build_facts("FIXA", "NSE", "x", "y", recs(), date(2026, 10, 20), price=300.0)
    assert "history_10y" in facts["not_available"]


def test_coverage_counts_symbols_with_each_metric():
    docs = {"A": {"valuation": {"pe": 10, "pb": None}, "quality": {"roe_pct": 5, "promoter_pct": None}},
            "B": {"valuation": {"pe": None, "pb": 2}, "quality": {"roe_pct": 6, "promoter_pct": 50}}}
    c = f.coverage(docs, universe=["A", "B", "C"])
    assert c["universe"] == 3 and c["with_facts"] == 2
    assert c["metrics"]["pe"] == {"count": 1, "pct": 33.3}
    assert c["metrics"]["roe_pct"]["count"] == 2


def test_collect_leaves_out_a_stock_with_no_raw_figure():
    from stockpilot.jobs.facts import collect
    day = date(2026, 11, 27)
    universe = [{"symbol": "AAA", "exchange": "NSE", "name": "A", "sector": ""},
                {"symbol": "BBB", "exchange": "NSE", "name": "B", "sector": ""}]
    # BBB's only record is not yet available on the day, so it has no figure
    later = [REC("sales", 1.0, period_end=date(2026, 9, 30), available_on=date(2027, 1, 1), source="nse")]
    out = collect(universe, lambda s: recs() if s == "AAA" else later, {}, day)
    assert [r["symbol"] for r in out] == ["AAA"]


def test_a_refused_publish_names_its_reason():
    import pytest

    from stockpilot.runtime.client import JobClient

    class Door:
        key, base_url = "k", "http://x"
        transport = staticmethod(lambda *a: (422, {"published": False, "reason": "fewer than 100 stocks"}))
    with pytest.raises(RuntimeError, match="fewer than 100 stocks"):
        JobClient(Door()).publish_finish("facts", "r1")
