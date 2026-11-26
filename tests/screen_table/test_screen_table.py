"""The universe table file: one row per listed stock, joined from the search index, stock facts and the nightly
mechanical results, in columns so the browser loads about 9,000 stocks in one small file."""
import json

from stockpilot.sources import screen_table as st

IDX = {"built_at": "2026-11-25T09:15:00+05:30", "entries": [
    {"symbol": "FIXA", "exchange": "NSE", "segment": "NSE", "name": "Fixture Alpha Ltd", "isin": "x", "aliases": []},
    {"symbol": "FIXD", "exchange": "BSE", "segment": "BSE_SME", "name": "Fixture Delta Industries", "isin": "y", "aliases": []},
]}
FACTS = {("FIXA", "NSE"): {"sector": "Fixture sector", "today": {"last": 103.0, "day_change_pct": 1.2},
                           "valuation": {"pe": 18.5, "market_cap_cr": 5200.0}, "quality": {"profit_growth_yoy_pct": 15.5}}}
MECH = {"results": [{"symbol": "FIXA", "exchange": "NSE", "chance_6m": 0.61}]}


def test_columns_line_up_and_gaps_are_null():
    t = st.build_table(IDX, FACTS, MECH, "2026-11-25T10:00:00+05:30")
    assert t["n"] == 2
    cols = [k for k in st.COLUMNS]
    assert all(len(t[c]) == 2 for c in cols)
    assert t["symbol"] == ["FIXA", "FIXD"] and t["segment"] == ["NSE", "BSE_SME"]
    assert (t["pe"][0], t["growth"][0], t["chance_6m"][0], t["mcap_cr"][0], t["sector"][0]) == (18.5, 15.5, 0.61, 5200.0, "Fixture sector")
    assert (t["pe"][1], t["growth"][1], t["chance_6m"][1], t["mcap_cr"][1], t["sector"][1]) == (None,) * 5


def test_nine_thousand_stocks_stay_small():
    idx = {"built_at": "t", "entries": [{"symbol": f"S{i}", "exchange": "NSE", "segment": "NSE", "name": f"Stock number {i} Ltd", "isin": "", "aliases": []} for i in range(9000)]}
    facts = {(f"S{i}", "NSE"): {"sector": "Sector %d" % (i % 30), "today": {"last": 100.5 + i, "day_change_pct": 1.23}, "valuation": {"pe": 20.1, "market_cap_cr": 1000.0 + i}, "quality": {"profit_growth_yoy_pct": 9.9}} for i in range(9000)}
    t = st.build_table(idx, facts, {"results": []}, "t")
    assert len(json.dumps(t, separators=(",", ":"))) < 1_200_000     # well inside Pages' per-file limit; gzip makes it a fraction


def test_contract_shape_matches_columns():
    c = json.load(open("schemas/live-contract.json"))["files"]["universe_table"]["shape"]
    assert set(st.COLUMNS) | {"built_at", "n"} == {k.rstrip("?") for k in c}
