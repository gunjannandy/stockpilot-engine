import json
from datetime import date
from pathlib import Path

from stockpilot import store

from stockpilot.sources import exchange

FIXTURES = Path(__file__).parents[1] / "fixtures"


def fixture_json(path: str):
    name = {"/api/holiday-master?type=trading": "nse_holidays.json",
            "/api/reportASM": "nse_asm.json", "/api/reportGSM": "nse_gsm.json"}[path]
    return json.loads((FIXTURES / name).read_text())


def test_trading_days_skip_weekends_and_nse_holidays(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    exchange.refresh_holidays(db, fixture_json)
    assert not exchange.is_trading_day(db, date(2026, 11, 24))   # holiday in NSE's list
    assert not exchange.is_trading_day(db, date(2026, 11, 22))   # Sunday
    assert exchange.is_trading_day(db, date(2026, 11, 23))


def test_surveillance_lists_name_each_flagged_stock_once(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    flagged = exchange.refresh_surveillance(db, date(2026, 11, 20), fixture_json)
    assert set(flagged) == {"AAATECH", "AAREYDRUGS", "AGIIL", "AGL", "AGSTRA", "ANKITMETAL"}
    assert flagged["AAATECH"] == "LTASM Stage I"
    assert flagged["AGSTRA"] == "GSM LXII"
    stored = dict(db.execute("select symbol, label from surveillance where as_of = ?", [date(2026, 11, 20)]).fetchall())
    assert stored == flagged
