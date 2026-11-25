"""Zerodha Console tax P&L (taxpnl .xlsx): realised gains per financial year, and the stage 7 check against ours.
The workbook is built in memory with the layout of the real files (checked on FY 2023-24 to 2025-26)."""
from datetime import date

from stockpilot import backup, store
from stockpilot.trades import consolepnl, feed
from xlsx_make import make_xlsx

HEAD = {"B": "Symbol", "C": "Quantity", "D": "Buy Value", "E": "Sell Value", "F": "Realized P&L"}


def sheet_equity(start="2025-04-01", end="2026-03-21", intraday=-3.0, short=-100.0, long=60.0, non_eq=10.0):
    return [{}, {"B": "Client ID", "C": "ZZ0000"}, {"B": "PAN", "C": "AAAAA0000A"}, {},
            {"B": f"Taxpnl Statement for Equity from {start} to {end}"}, {},
            {"B": "Realized Profit Breakdown"}, {},
            {"B": "Intraday/Speculative profit", "C": str(intraday)}, {"B": "Short Term profit", "C": str(short)},
            {"B": "Long Term profit", "C": str(long)}, {"B": "Non Equity profit", "C": str(non_eq)}, {},
            {"B": "Charges"}, {"B": "Account Head", "C": "Amount"}, {"B": "Brokerage - Z", "C": "1.5"}, {},
            {"B": "Intraday"}, {}, HEAD,
            {"B": "AAA", "C": "1", "D": "10", "E": "7", "F": str(intraday)}, {},
            {"B": "Short Term Trades"}, {}, HEAD,
            {"B": "BBB", "C": "5", "D": "100", "E": "40", "F": "-60"},
            {"B": "CCC", "C": "2", "D": "50", "E": "10", "F": "-40"}, {},
            {"B": "Long Term Trades"}, {}, HEAD,
            {"B": "DDD", "C": "3", "D": "30", "E": "90", "F": str(long)}, {},
            {"B": "Non Equity"}, {}, HEAD,
            {"B": "GOLDETF", "C": "1", "D": "5", "E": "15", "F": str(non_eq)}]


def sheet_mf():
    return [{}, {"B": "Taxpnl Statement for Mutual Funds from 2025-04-01 to 2026-03-21"}, {},
            {"B": "Realized Profit Breakdown"}, {},
            {"B": "Short Term profit Equity", "C": "0.0"}, {"B": "Long Term profit Equity", "C": "35.5"},
            {"B": "Short Term profit Debt", "C": "0.0"}, {"B": "Long Term profit Debt", "C": "0.0"}, {},
            {"B": "Long Term Trades Equity"}, {}, HEAD,
            {"B": "SOME FUND - DIRECT PLAN GROWTH", "C": "1", "D": "53", "E": "88.5", "F": "35.5"}, {},
            {"B": "Short Term Trades Debt"}, {}, HEAD]


def book(**kw):
    return make_xlsx({"Tradewise Exits from 2025-04-01": [{}], "Equity and Non Equity": sheet_equity(**kw),
                      "Mutual Funds": sheet_mf(), "F&O": [{}]})


def test_equity_and_mf_sheets_give_one_statement_each_with_the_financial_year():
    out = consolepnl.parse(book())
    assert {(s.segment, s.fy, s.period_end) for s in out} == {("equity", "2025-26", date(2026, 3, 21)),
                                                              ("mf", "2025-26", date(2026, 3, 21))}
    eq = next(s for s in out if s.segment == "equity")
    assert eq.totals == {"intraday": -3.0, "short_term": -100.0, "long_term": 60.0, "non_equity": 10.0}
    assert [(r.category, r.symbol, r.realised) for r in eq.rows] == [
        ("intraday", "AAA", -3.0), ("short_term", "BBB", -60.0), ("short_term", "CCC", -40.0),
        ("long_term", "DDD", 60.0), ("non_equity", "GOLDETF", 10.0)]
    assert eq.problems == []
    mf = next(s for s in out if s.segment == "mf")
    assert mf.totals["long_term_equity"] == 35.5 and mf.rows[0].category == "long_term_equity"


def test_rows_that_do_not_add_up_to_the_breakdown_are_reported_not_hidden():
    [eq, _] = consolepnl.parse(book(short=-90.0))
    assert any("short_term" in p for p in eq.problems)


def test_old_layout_summary_and_isin_columns_gives_a_total_per_stock():
    old = [{"B": "P&L Statement for Equity from 2022-04-01 to 2023-03-31"}, {}, {"B": "Summary"}, {},
           {"B": "Charges", "C": "9"}, {"B": "Other Credit & Debit", "C": "-5"}, {"B": "Realized P&L", "C": "-155.65"},
           {"B": "Unrealized P&L", "C": "74"}, {},
           {"B": "Symbol", "C": "ISIN", "D": "Quantity", "E": "Buy Value", "F": "Sell Value", "G": "Realized P&L"},
           {"B": "AAA", "C": "INE000A01010", "D": "10", "E": "100", "F": "40", "G": "-60"},
           {"B": "BBB", "C": "INE000B01010", "D": "0", "E": "0", "F": "0", "G": "0"}]
    [s] = consolepnl.parse(make_xlsx({"Equity": old, "Other Debits and Credits": [{}]}))
    assert (s.segment, s.fy, s.totals) == ("equity", "2022-23", {"total": -155.65})
    assert [(r.category, r.symbol, r.isin, r.realised) for r in s.rows] == [("total", "AAA", "INE000A01010", -60.0),
                                                                           ("total", "BBB", "INE000B01010", 0.0)]
    assert len(s.problems) == 1   # -60 against the stated -155.65: shown, not hidden


def test_new_layout_rows_get_their_isin_from_the_tradewise_sheet():
    # the newer files print no ISIN beside the stock, but the "Tradewise Exits" sheet lists symbol and ISIN per exit
    tradewise = [{}, {"B": "Symbol", "C": "ISIN", "D": "Entry Date"},
                 {"B": "BBB", "C": "INE000B01010", "D": "2025-05-01"}, {"B": "BBB", "C": "INE000B01010", "D": "2025-06-01"},
                 {"B": "DDD", "C": "INE000D01010", "D": "2024-01-01"}]
    data = make_xlsx({"Tradewise Exits from 2025-04-01": tradewise, "Equity and Non Equity": sheet_equity(), "Mutual Funds": sheet_mf()})
    [eq, _] = consolepnl.parse(data)
    assert {r.symbol: r.isin for r in eq.rows} == {"AAA": None, "BBB": "INE000B01010", "CCC": None, "DDD": "INE000D01010",
                                                  "GOLDETF": None}


def test_a_file_that_is_not_a_console_statement_fails_loudly():
    import pytest
    with pytest.raises(ValueError):
        consolepnl.parse(make_xlsx({"Sheet1": [{"B": "Timeline"}]}))


def test_store_keeps_the_newer_file_when_two_cover_one_year(tmp_path):
    db = store.open(tmp_path / "a.duckdb")
    consolepnl.save(db, consolepnl.parse(book(non_eq=10.0)), "d1", "2024-07-02T00:00:00Z")
    consolepnl.save(db, consolepnl.parse(book(non_eq=10.0)), "d1", "2024-07-02T00:00:00Z")   # twice adds nothing
    assert db.execute("select count(*) from console_pnl_totals").fetchone()[0] == 8   # 4 equity + 4 fund
    consolepnl.save(db, consolepnl.parse(book(non_eq=25.0)), "d2", "2026-03-21T00:00:00Z")   # newer wins
    consolepnl.save(db, consolepnl.parse(book(non_eq=99.0)), "d1", "2024-07-02T00:00:00Z")   # older never overwrites
    assert db.execute("select profit, source_ref from console_pnl_totals where fy = '2025-26' "
                      "and segment = 'equity' and category = 'non_equity'").fetchone() == (25.0, "d2")
    assert db.execute("select count(*) from console_pnl where source_ref = 'd1'").fetchone()[0] == 0


def test_the_new_tables_are_in_state_backup():
    assert {"console_pnl", "console_pnl_totals"} <= set(backup.STATE_TABLES)


def test_feed_routes_a_taxpnl_workbook_and_store_all_saves_it(tmp_path):
    from test_trades_feed import FakeBridge
    item = {"source": "drive", "id": "x1", "name": "taxpnl 2025-2026.xlsx", "mime": "application/vnd.ms-excel",
            "size": 1, "modified": "2026-03-21T06:25:06.000Z"}
    bridge = FakeBridge([item], {"x1": book()}, {})
    result = feed.fetch(bridge, "ABCDE1234F", None)
    assert result.failed == [] and result.ignored == [] and result.skipped == []
    db = store.open(tmp_path / "a.duckdb")
    feed.store_all(db, result)
    assert db.execute("select count(*) from console_pnl_totals").fetchone()[0] == 8


def plain(rows):
    return "\n".join(rows)


def our(kind, term, bucket, proceeds, cost, sold=date(2025, 8, 1)):
    return {"kind": kind, "term": term, "bucket": bucket, "proceeds": proceeds, "cost": cost, "sold_on": sold,
            "gain": proceeds - cost}


def test_check_says_nothing_when_ours_match_and_lists_each_difference_in_words(tmp_path):
    db = store.open(tmp_path / "a.duckdb")
    consolepnl.save(db, consolepnl.parse(book()), "d1", "2026-03-21T00:00:00Z")
    match = [our("stock", "short", "equity", 47, 147), our("stock", "long", "equity", 90, 30),
             our("stock", "short", "gold", 15, 5), our("mf", "long", "equity", 88.5, 53)]
    assert consolepnl.check(db, 2025, match) == []
    off = [our("stock", "short", "equity", 47, 347), our("stock", "long", "equity", 90, 30),
           our("stock", "short", "gold", 15, 5), our("mf", "long", "equity", 88.5, 53),
           our("stock", "short", "equity", 10, 5, sold=date(2026, 3, 30))]   # after the file's end: not compared
    notes = consolepnl.check(db, 2025, off)
    assert len(notes) == 1 and "short-term" in notes[0] and "2025-26" in notes[0] and "₹197" in notes[0]


def share(isin, symbol, gain):
    return {"kind": "stock", "term": "short", "bucket": "equity", "proceeds": 100 + gain, "cost": 100, "sold_on": date(2025, 8, 1),
            "gain": gain, "isin": isin, "symbol": symbol}


def per_share_db(tmp_path):
    db = store.open(tmp_path / "a.duckdb")
    db.execute("insert into console_pnl_totals values ('2025-26', 'equity', 'short_term', -5000, '2026-03-21', 'd1', '')")
    for symbol, isin, gain in [("TWL", "INE000T01011", -2000.0), ("BBB", "INE000B01010", -3000.0)]:
        db.execute("insert into console_pnl values ('2025-26', 'equity', 'short_term', ?, ?, 1, 0, 0, ?, 'd1')", [symbol, isin, gain])
    return db


def test_a_renamed_symbol_is_the_same_share_when_compared_by_isin(tmp_path):
    db = per_share_db(tmp_path)
    ours = [share("INE000T01011", "TITAGARH", -2000.0), share("INE000B01010", "BBB", -3000.0)]   # Console says TWL
    assert consolepnl.check(db, 2025, ours) == []


def test_per_share_differences_are_listed_by_name_and_a_rename_does_not_hide_a_real_gap(tmp_path):
    db = per_share_db(tmp_path)
    ours = [share("INE000T01011", "TITAGARH", -2000.0), share("INE000B01010", "BBB", -2400.0),
            share("INE000Z01010", "ZZZ", 700.0)]                                   # we sold a share Console never saw
    notes = [n for n in consolepnl.check(db, 2025, ours) if n.startswith("Share by share")]
    assert len(notes) == 1
    assert "BBB" in notes[0] and "-₹3,000" in notes[0] and "-₹2,400" in notes[0]
    assert "ZZZ" in notes[0] and "TITAGARH" not in notes[0] and "TWL" not in notes[0]


def test_check_without_a_console_file_for_the_year_has_nothing_to_say(tmp_path):
    db = store.open(tmp_path / "a.duckdb")
    assert consolepnl.check(db, 2025, []) == []


def test_weekly_tax_notes_carry_the_console_check_and_never_fail(tmp_path):
    from stockpilot import weekly
    db = store.open(tmp_path / "a.duckdb")
    assert weekly.console_notes(db, [], [], 2026, None) == []   # no Console file: nothing to say
    consolepnl.save(db, consolepnl.parse(book()), "d1", "2026-03-21T00:00:00Z")
    notes = weekly.console_notes(db, [], [], 2026, None)       # FY 2026-27 has no file: the last one (2025-26) is used
    assert any("2025-26" in n and "short-term" in n for n in notes)
    assert weekly.console_notes(db, None, [], 2025, None)[0].startswith("The check against Console")


def sheet_mf_real_layout(rows_debt_post=()):
    """The Mutual Funds sheet as Zerodha prints it (checked on the FY 2023-24 to 2025-26 files): all five breakdown
    lines, and every section heading even when it holds no rows. Identity lines are made up."""
    sections = [{"B": "Short Term Trades Equity"}, {}, HEAD, {}, {"B": "Long Term Trades Equity"}, {}, HEAD,
                {"B": "SOME FUND - DIRECT PLAN GROWTH", "C": "1", "D": "53.1", "E": "88.8", "F": "35.7"}, {},
                {"B": "Short Term Trades Debt"}, {}, HEAD, {}, {"B": "Long Term Trades Debt"}, {}, HEAD, {},
                {"B": "Debt - Purchases post 2023-04-01"}, {}, HEAD, *rows_debt_post]
    return [{}, {"B": "Client ID", "C": "ZZ0000"}, {"B": "PAN", "C": "AAAAA0000A"}, {},
            {"B": "Taxpnl Statement for Mutual Funds from 2024-04-01 to 2025-03-31"}, {},
            {"B": "Realized Profit Breakdown"}, {},
            {"B": "Short Term profit Equity", "C": "0.0000"}, {"B": "Long Term profit Equity", "C": "35.7"},
            {"B": "Short Term profit Debt", "C": "0.0000"}, {"B": "Long Term profit Debt", "C": "0.0000"},
            {"B": "Debt - Purchases post 2023-04-01", "C": "12.5"}, {}, {"B": "Charges"}, {},
            {"B": "Account Head", "C": "Amount"}, {"B": "Other Charges"}, {}, *sections]


def test_the_real_mutual_fund_layout_gives_its_rows_and_checks_the_post_2023_debt_total():
    data = make_xlsx({"Mutual Funds": sheet_mf_real_layout(
        [{"B": "SOME DEBT FUND - DIRECT", "C": "2", "D": "100", "E": "112.5", "F": "12.5"}])})
    [mf] = consolepnl.parse(data)
    assert [(r.category, r.realised) for r in mf.rows] == [("long_term_equity", 35.7), ("debt_post_2023", 12.5)]
    assert mf.totals["debt_post_2023"] == 12.5
    assert mf.problems == []


def test_a_year_with_no_fund_sales_is_an_empty_statement_not_an_error():
    [mf] = consolepnl.parse(make_xlsx({"Mutual Funds": [{}, {"B": "Taxpnl Statement for Mutual Funds from 2025-04-01 "
                                                              "to 2026-03-21"}, {}, {"B": "Realized Profit Breakdown"},
                                                          {"B": "Long Term profit Equity", "C": "0.0000"}, {},
                                                          {"B": "Long Term Trades Equity"}, {}, HEAD]}))
    assert mf.rows == [] and mf.totals == {"long_term_equity": 0.0} and mf.problems == []
