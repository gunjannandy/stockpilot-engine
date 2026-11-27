"""What the account holds: lots from the documents first, Kite and the CDSL statement as the check and the gap-fill."""
from datetime import date, datetime

import pytest

from helpers import insert_prices
from stockpilot import store
from stockpilot.book import positions

DAY = date(2026, 11, 20)


@pytest.fixture
def db(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    db.execute("insert into stocks values ('TCS', 'Tata Consultancy Services', 'IT', 'INE467B01029'), "
               "('NEWIPO', 'New Listing Ltd', 'Misc', 'INE000N01011')")
    insert_prices(db, [(DAY, "TCS", "NSE", "EQ", 0, 0, 0, 4000.0, 0, 0, 0, 0),
                       (DAY, "NEWIPO", "NSE", "EQ", 0, 0, 0, 150.0, 0, 0, 0, 0),
                       (DAY, "NOW", "NYSE", "", 0, 0, 0, 1000.0, 0, 0, 0, 0)])
    db.execute("insert into fx values (?, 'USDINR', 85.0)", [DAY])
    return db


def lot(db, symbol, isin, on, qty, cost, kind="stock", currency="INR", closed=0):
    db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, currency, closed_quantity, "
               "source) values (?, ?, ?, ?, ?, ?, ?, ?, 'trades:test')", [kind, symbol, isin, on, qty, cost, currency, closed])


def kite(db, symbol, isin, qty, avg, kind="stock"):
    db.execute("insert into holdings values (?, ?, ?, ?, ?, ?, 'kite')", [datetime(2026, 11, 20, 9), kind, symbol, isin, qty, avg])


def test_with_no_kite_login_the_lots_are_the_holdings(db):
    lot(db, "TCS", "INE467B01029", date(2025, 1, 10), 10, 3000.0)
    lot(db, "TCS", "INE467B01029", date(2026, 6, 1), 20, 3600.0, closed=10)   # 10 of these already sold
    [p] = positions.held(db, DAY)
    assert (p.symbol, p.name, p.kind, p.quantity, p.source) == ("TCS", "Tata Consultancy Services", "equity", 20, "lots")
    assert p.avg_cost == pytest.approx(3300.0) and p.price == 4000.0 and p.value == pytest.approx(80_000)
    assert [(l.quantity, l.turns_long_term_on) for l in p.lots] == [(10, date(2026, 1, 11)), (10, date(2027, 6, 2))]
    assert [l.long_term(DAY) for l in p.lots] == [True, False] and p.check is None


def test_a_kite_holding_with_no_lots_still_shows(db):
    kite(db, "NEWIPO", "INE000N01011", 50, 140.0)       # an IPO allotment: no contract note
    [p] = positions.held(db, DAY)
    assert (p.symbol, p.quantity, p.avg_cost, p.source, p.lots) == ("NEWIPO", 50, 140.0, "kite", [])


def test_when_kite_disagrees_kite_decides_the_units_and_the_gap_is_named(db):
    lot(db, "TCS", "INE467B01029", date(2025, 1, 10), 10, 3000.0)
    kite(db, "TCS", "INE467B01029", 12, 3100.0)
    [p] = positions.held(db, DAY)
    assert p.quantity == 12 and p.check == "Documents explain 10 of 12 units."


def test_without_kite_the_depository_statement_fills_a_gap(db):
    db.execute("insert into holding_statements values ('2026-10-31', 'INE000N01011', 50)")
    [p] = positions.held(db, DAY)
    assert (p.symbol, p.quantity, p.avg_cost, p.source, p.price) == ("NEWIPO", 50, None, "statement", 150.0)


def test_foreign_shares_are_priced_and_costed_in_rupees(db):
    lot(db, "NOW", "US81762P1021", date(2025, 3, 1), 4, 800.0, kind="rsu", currency="USD")
    [p] = positions.held(db, DAY)
    assert p.kind == "foreign" and p.avg_cost == pytest.approx(68_000) and p.price == pytest.approx(85_000)
    assert p.lots[0].turns_long_term_on == date(2027, 3, 2)          # 24 months for foreign shares


def test_a_renamed_company_shows_under_its_current_nse_symbol(db):
    db.execute("insert into stocks values ('ABREL', 'Aditya Birla Real Estate', 'Realty', 'INE055A01016')")
    lot(db, "CENTURYTEX", "INE055A01016", date(2023, 5, 2), 8, 900.0)    # the contract note used the old name
    kite(db, "ABREL-BE", "INE055A01016", 8, 900.0)                       # Kite adds the series
    [p] = positions.held(db, DAY)
    assert (p.symbol, p.name, p.check) == ("ABREL", "Aditya Birla Real Estate", None)


def test_an_etf_keeps_its_trading_symbol_and_a_fund_keeps_its_name(db):
    db.execute("insert into funds values (1, 'INF204KB17I5', null, 'Nippon India ETF Nifty BeES', 'Direct', 'Growth', "
               "'Other Scheme - Index Funds', ''), (2, 'INF879O01027', null, 'Parag Parikh Flexi Cap Fund', 'Direct', "
               "'Growth', 'Equity Scheme - Flexi Cap Fund', '')")
    lot(db, "NIFTYBEES", "INF204KB17I5", date(2024, 1, 5), 100, 230.0)
    lot(db, "PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN", "INF879O01027", date(2024, 1, 5), 50, 60.0, kind="mf")
    got = {(p.kind, p.symbol, p.name) for p in positions.held(db, DAY)}
    assert got == {("equity", "NIFTYBEES", "Nippon India ETF Nifty BeES"),
                   ("mf", "INF879O01027", "Parag Parikh Flexi Cap Fund")}


class Counting:
    def __init__(self, db):
        self.db, self.queries = db, 0

    def execute(self, *a, **k):
        self.queries += 1
        return self.db.execute(*a, **k)

    def __getattr__(self, name):
        return getattr(self.db, name)


def _many(db, n):
    for i in range(n):
        symbol, isin = f"S{i}", f"INE{i:06d}01010"
        db.execute("insert into stocks values (?, ?, 'Misc', ?)", [symbol, symbol, isin])
        insert_prices(db, [(DAY, symbol, "NSE", "EQ", 0, 0, 0, 100.0 + i, 0, 0, 0, 0)])
        lot(db, symbol, isin, date(2025, 1, 10), 10, 90.0)
        lot(db, symbol, isin, date(2026, 3, 10), 5, 95.0)


def test_held_asks_the_same_number_of_questions_for_3_or_70_holdings(db):
    _many(db, 3)
    small = Counting(db)
    three = positions.held(small, DAY)
    _many_more = 70
    for i in range(3, _many_more):
        symbol, isin = f"S{i}", f"INE{i:06d}01010"
        db.execute("insert into stocks values (?, ?, 'Misc', ?)", [symbol, symbol, isin])
        insert_prices(db, [(DAY, symbol, "NSE", "EQ", 0, 0, 0, 100.0 + i, 0, 0, 0, 0)])
        lot(db, symbol, isin, date(2025, 1, 10), 10, 90.0)
        lot(db, symbol, isin, date(2026, 3, 10), 5, 95.0)
    big = Counting(db)
    seventy = positions.held(big, DAY)
    assert len(three) == 3 + 0 and len(seventy) == 70
    assert small.queries == big.queries
    assert all(p.price == 100.0 + int(p.symbol[1:]) for p in seventy)


def test_prices_come_from_the_nse_first_then_bse_then_the_latest_day_on_or_before(db):
    lot(db, "TCS", "INE467B01029", date(2025, 1, 10), 1, 3000.0)
    insert_prices(db, [(DAY, "TCS", "BSE", "EQ", 0, 0, 0, 3999.0, 0, 0, 0, 0)])
    [p] = positions.held(db, DAY)
    assert p.price == 4000.0                       # NSE wins a tie
    [p] = positions.held(db, date(2026, 11, 25))
    assert p.price == 4000.0                       # the latest close on or before the day
    [p] = positions.held(db, date(2026, 11, 1))
    assert p.price is None
