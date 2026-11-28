"""C-047-1: the universe keeps delisted and renamed fixtures."""
from stockpilot.jobs.universe import to_rows


def _e(sym, name, aliases=()):
    return {"exchange": "NSE", "symbol": sym, "segment": "main", "name": name, "isin": "", "aliases": list(aliases)}


def _p(sym, name, aliases=""):
    return {"id": f"NSE:{sym}", "symbol": sym, "exchange": "NSE", "segment": "main", "name": name, "isin": "",
            "aliases": aliases, "status": "listed"}


def test_delisted_stock_is_kept_marked_delisted():
    rows = {r["id"]: r for r in to_rows([_e("AAA", "Alpha Ltd")], [_p("AAA", "Alpha Ltd"), _p("GONE", "Gone Ltd")])}
    assert rows["NSE:GONE"]["status"] == "delisted" and rows["NSE:AAA"]["status"] == "listed"


def test_renamed_stock_keeps_its_old_name_searchable():
    rows = {r["id"]: r for r in to_rows([_e("AAA", "Alpha New Ltd")], [_p("AAA", "Alpha Old Ltd")])}
    r = rows["NSE:AAA"]
    assert r["name"] == "Alpha New Ltd" and "Alpha Old Ltd" in r["aliases"].split("|")
