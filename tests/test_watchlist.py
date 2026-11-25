from stockpilot import store, watchlist


def test_import_adds_each_symbol_once_and_is_repeatable(tmp_path):
    csv = tmp_path / "wl.csv"
    csv.write_text("symbol,exchange,source\nSBIN,NSE,kite\nPENINLAND,BSE,kite\nPENINLAND,NSE,kite\nSBIN,NSE,kite\n")
    db = store.open(tmp_path / "sp.duckdb")
    assert watchlist.import_csv(db, csv) == 3
    assert watchlist.import_csv(db, csv) == 0
    assert watchlist.active(db) == [("PENINLAND", "BSE"), ("PENINLAND", "NSE"), ("SBIN", "NSE")]


def test_removed_symbols_leave_the_active_list(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    watchlist.add(db, "SBIN", "NSE", by="father")
    watchlist.remove(db, "SBIN", "NSE", by="father")
    assert watchlist.active(db) == []
    watchlist.add(db, "SBIN", "NSE", by="father")   # undo
    assert watchlist.active(db) == [("SBIN", "NSE")]
