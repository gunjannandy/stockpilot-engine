"""Lane B step 3: Kite decides what the account owns and how many units; the documents add cost, dates and tax."""
from datetime import date, datetime

import pytest

from helpers import insert_prices
from stockpilot import store
from stockpilot.book import positions

DAY = date(2026, 11, 20)
PPFAS, OTHER_FUND = "INF879O01027", "INF732E01037"


@pytest.fixture
def db(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    db.execute("insert into stocks values ('TCS', 'Tata Consultancy Services', 'IT', 'INE467B01029'), "
               "('NIFTYBEES', 'Nippon India ETF Nifty BeES', 'ETF', 'INF204KB17I5')")
    db.execute("insert into funds values (1, ?, null, 'Parag Parikh Flexi Cap Fund', 'Direct', 'Growth', "
               "'Equity Scheme - Flexi Cap Fund', ''), (2, ?, null, 'Some Other Fund', 'Direct', 'Growth', "
               "'Debt Scheme - Liquid Fund', ''), (3, 'INF204KB17I5', null, 'Nippon ETF', 'Direct', 'Growth', 'Other', '')",
               [PPFAS, OTHER_FUND])
    insert_prices(db, [(DAY, "TCS", "NSE", "EQ", 0, 0, 0, 4000.0, 0, 0, 0, 0)])
    return db


def lot(db, symbol, isin, on, qty, cost, kind="stock", currency="INR", closed=0):
    db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, currency, closed_quantity, "
               "source) values (?, ?, ?, ?, ?, ?, ?, ?, 'trades:test')", [kind, symbol, isin, on, qty, cost, currency, closed])


def kite(db, symbol, isin, qty, avg, kind="stock"):
    db.execute("insert into holdings values (?, ?, ?, ?, ?, ?, 'kite')", [datetime(2026, 11, 20, 9), kind, symbol, isin, qty, avg])


def by_symbol(db):
    return {p.symbol: p for p in positions.held(db, DAY)}


def test_units_missing_from_the_documents_are_costed_from_kites_average(db):
    lot(db, "TCS", "INE467B01029", date(2025, 1, 10), 10, 3000.0)
    kite(db, "TCS", "INE467B01029", 12, 3100.0)
    p = by_symbol(db)["TCS"]
    assert p.quantity == 12 and p.avg_cost == pytest.approx(3100.0)        # 12 x 3,100 in all; the lots hold 10 x 3,000 of it
    assert [(l.quantity, l.cost) for l in p.lots] == [(10, 3000.0)] and p.source == "kite"


def test_the_parag_parikh_gap_shows_all_of_kites_units(db):
    lot(db, PPFAS, PPFAS, date(2024, 1, 5), 4890.044, 60.0, kind="mf")
    kite(db, PPFAS, PPFAS, 7162.094, 70.0, kind="mf")
    p = by_symbol(db)[PPFAS]
    assert p.quantity == pytest.approx(7162.094) and p.name == "Parag Parikh Flexi Cap Fund"
    assert p.check == "Documents explain 4890.04 of 7162.09 units."
    assert p.avg_cost == pytest.approx(70.0)


def test_documents_that_show_more_than_kite_are_trimmed_oldest_first(db):
    lot(db, "TCS", "INE467B01029", date(2024, 1, 10), 10, 3000.0)
    lot(db, "TCS", "INE467B01029", date(2026, 6, 1), 20, 3600.0)
    kite(db, "TCS", "INE467B01029", 20, 3600.0)
    p = by_symbol(db)["TCS"]
    assert p.quantity == 20 and [(l.acquired_on, l.quantity) for l in p.lots] == [(date(2026, 6, 1), 20)]
    assert p.check == "Documents show 30 units; Kite shows 20."


def test_a_holding_only_the_documents_know_is_not_shown_once_kite_has_spoken(db):
    lot(db, "TCS", "INE467B01029", date(2024, 1, 10), 10, 3000.0)
    kite(db, "OTHER", "INE000X01011", 5, 10.0)
    assert "TCS" not in by_symbol(db)


def test_us_shares_are_not_kites_to_decide(db):
    lot(db, "NOW", "US81762P1021", date(2026, 2, 9), 6, 100.0, kind="rsu", currency="USD")
    db.execute("insert into fx values (?, 'USDINR', 90.0)", [DAY])
    kite(db, "TCS", "INE467B01029", 1, 3000.0)
    p = by_symbol(db)["NOW"]
    assert p.quantity == 6 and p.check is None and p.kind == "foreign"


def test_a_fund_only_the_depository_knows_is_shown_even_with_a_kite_snapshot(db):
    kite(db, "TCS", "INE467B01029", 1, 3000.0)
    db.execute("insert into holding_statements values ('2026-10-31', ?, 0.195)", [OTHER_FUND])
    p = by_symbol(db)[OTHER_FUND]
    assert (p.kind, p.quantity, p.source, p.name) == ("mf", 0.195, "statement", "Some Other Fund")


def test_a_share_or_etf_only_the_depository_knows_stays_hidden_when_kite_has_spoken(db):
    kite(db, "TCS", "INE467B01029", 1, 3000.0)
    db.execute("insert into holding_statements values ('2026-10-31', 'INF204KB17I5', 50), ('2026-10-31', 'INE000Z01019', 7)")
    assert set(by_symbol(db)) == {"TCS"}
