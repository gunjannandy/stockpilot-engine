"""Fund research reads a clean plain-English group, not AMFI's two spellings of every category."""
from stockpilot import fundgroups, store
from stockpilot.sources import navhistory as nh


def test_both_amfi_spellings_give_one_group():
    assert fundgroups.group_of("Equity Scheme - Flexi Cap Fund", "X") == fundgroups.group_of("Equity Schemes - Flexi Cap Fund", "X") == "Flexi cap"
    assert fundgroups.group_of("Equity Scheme - Large & Mid Cap Fund", "X") == "Large & mid cap"
    assert fundgroups.group_of("Equity Schemes - ELSS- Tax Saver Fund", "X") == "Tax saving (ELSS)"
    assert fundgroups.group_of("Hybrid Schemes - Balanced Advantage Fund/ Dynamic Asset Allocation", "X") == "Balanced advantage"


def test_an_index_fund_is_researched_only_when_it_tracks_a_main_index():
    assert fundgroups.group_of("Other Scheme - Index Funds", "UTI Nifty 50 Index Fund") == "Index (Nifty 50, Sensex)"
    assert fundgroups.group_of("Other Scheme - Index Funds", "Navi Nifty Midcap 150 Index Fund") == "Index (mid and small cap)"
    assert fundgroups.group_of("Other Scheme - Index Funds", "Some Nifty Realty Index Fund") is None


def test_sectoral_debt_and_arbitrage_are_not_researched():
    for cat in ("Equity Scheme - Sectoral/ Thematic", "Debt Scheme - Liquid Fund", "Hybrid Scheme - Arbitrage Fund", "Income"):
        assert fundgroups.group_of(cat, "X") is None


def test_scope_adds_the_researched_groups_even_with_no_fund_held(tmp_path):
    db = store.open(tmp_path / "t.duckdb", job="test")
    rows = [(1, "Direct Plan", "Growth", "Equity Scheme - Mid Cap Fund"), (2, "Regular Plan", "Growth", "Equity Scheme - Mid Cap Fund"),
            (3, "Direct Plan", "IDCW", "Equity Scheme - Mid Cap Fund"), (4, "Direct Plan", "Growth", "Equity Scheme - Sectoral/ Thematic")]
    for code, plan, opt, cat in rows:
        db.execute("insert into funds values (?, ?, null, ?, ?, ?, ?, 'H')", [code, f"INF{code:03d}", f"Fund {code}", plan, opt, cat])
    assert nh.scope(db) == [1]
