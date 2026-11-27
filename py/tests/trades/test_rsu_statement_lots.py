"""Lane R: Fidelity's 'Current Shares' lots, once parsed and stored, replace the documents' lots up to the statement day
(real, not estimated); vests after it stay from the documents; the rest of Fidelity's count is still one estimated lot."""
from datetime import date

from pytest import approx

from stockpilot import store
from stockpilot.book import positions
from stockpilot.trades import fidelity_lots, lots
from fidelity_pdf import ROWS, make

ISIN = "US81762P1021"
AS_OF = date(2025, 12, 31)


def seed(db, holding_qty=20.0, holding_basis=200000.10):
    for d in (date(2024, 8, 16), date(2025, 11, 14), date(2026, 2, 9), date(2025, 12, 31), date(2026, 11, 24), date(2024, 8, 17), date(2025, 11, 17)):
        db.execute("insert into fx values (?, 'USDINR', 80.0)", [d])
    # documents' version of the first two lots: different dates and sizes (documents are dated by delivery)
    for key, day, qty, price in (("a", date(2024, 8, 16), 12.0, 100.0), ("b", date(2025, 11, 14), 6.0, 90.0), ("c", date(2026, 2, 9), 3.0, 70.0)):
        lots.save_trades(db, [lots.Trade("fidelity_docs", key, "rsu", "NOW", ISIN, "vest", day, qty, price, "USD", trade_key=key)])
    db.execute("insert into fidelity_holdings values (?, 'NOW', ?, ?, ?, 1.0, 91.28)", [date(2026, 11, 24), ISIN, holding_qty, holding_basis])


def test_ingest_stores_lots_and_reports_real(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    seed(db)
    res = fidelity_lots.ingest(db, make(ROWS), AS_OF)
    assert res.stored == 2 and res.consistent
    assert db.execute("select count(*), sum(quantity) from fidelity_lots").fetchone() == (2, 15.5)
    assert fidelity_lots.ingest(db, make(ROWS), AS_OF).stored == 0          # idempotent


def test_statement_lots_replace_the_documents_up_to_the_statement_day(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    seed(db)
    fidelity_lots.ingest(db, make(ROWS), AS_OF)
    lots.rebuild(db)
    rows = db.execute("select acquired_on, quantity, source, estimated from lots where kind = 'rsu' order by 1").fetchall()
    assert rows[:2] == [(date(2024, 8, 17), 10.0, "trades:fidelity_statement", False),
                        (date(2025, 11, 17), 5.5, "trades:fidelity_statement", False)]
    assert rows[2] == (date(2026, 2, 9), 3.0, "trades:fidelity_docs", False)          # after the statement: from the documents
    assert rows[3][1] == approx(20.0 - 15.5 - 3.0) and rows[3][3] is True             # what is still missing: one estimate
    now = [p for p in positions.held(db, date(2026, 11, 25)) if p.symbol == "NOW"][0]
    assert now.quantity == approx(20.0)


def test_the_cost_in_rupees_is_the_statements_not_a_rate_guess(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    seed(db)
    fidelity_lots.ingest(db, make(ROWS), AS_OF)
    lots.rebuild(db)
    usd, qty = db.execute("select cost_per_unit, quantity from lots where acquired_on = '2024-08-17'").fetchone()
    assert usd * qty * 80.0 == approx(100000.10, rel=1e-6)


def test_a_statement_with_more_shares_than_fidelity_now_holds_is_ignored(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    seed(db, holding_qty=10.0, holding_basis=50000.0)
    res = fidelity_lots.ingest(db, make(ROWS), AS_OF)
    assert res.stored == 0 and not res.consistent
