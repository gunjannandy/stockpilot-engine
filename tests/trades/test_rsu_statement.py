"""RSU count truth: Fidelity's own current statement (an owner screenshot of the Stock Plan page) beats the vest documents,
which stop at the last document. The shares it shows beyond the documents become one estimated lot whose cost makes the
total match Fidelity's cost basis."""
from datetime import date

from pytest import approx

from stockpilot import store
from stockpilot.book import positions
from stockpilot.trades import lots


def vest(db, day, qty, price):
    lots.save_trades(db, [lots.Trade("fidelity_docs", f"v-{day}", "rsu", "NOW", "US81762P1021", "vest", day, qty, price, "USD",
                                     trade_key=f"v-{day}")])


def seed(db):
    for d, r in ((date(2026, 2, 9), 90.0), (date(2026, 11, 24), 92.0)):
        db.execute("insert into fx values (?, 'USDINR', ?)", [d, r])
    vest(db, date(2026, 2, 9), 10.0, 100.0)               # documented: 10 shares, $1,000 = Rs 90,000
    db.execute("insert into fidelity_holdings values (?, 'NOW', 'US81762P1021', 15.0, 138000.0, 1380000.0, 91.28)",
               [date(2026, 11, 24)])                       # Fidelity: 15 shares, cost basis Rs 1,38,000


def test_the_shares_the_documents_miss_become_one_estimated_lot_priced_from_fidelitys_cost_basis(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    seed(db)
    lots.rebuild(db)
    est = db.execute("select symbol, quantity, estimated, currency, acquired_on, source from lots where estimated").fetchall()
    assert est == [("NOW", 5.0, True, "USD", date(2026, 11, 24), "trades:estimated")]
    cost_inr = db.execute("select cost_per_unit from lots where estimated").fetchone()[0] * 92.0
    assert cost_inr * 5 == approx(138000.0 - 90000.0, rel=1e-4)       # the rest of Fidelity's basis, at the statement-day rate


def test_the_holding_then_shows_fidelitys_share_count(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    seed(db)
    lots.rebuild(db)
    now = [p for p in positions.held(db, date(2026, 11, 25)) if p.symbol == "NOW"]
    assert now[0].quantity == 15.0 and "Estimated" in (now[0].check or "")


def test_no_estimate_when_documents_already_explain_fidelitys_count(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    seed(db)
    vest(db, date(2026, 5, 15), 5.0, 95.0)
    lots.rebuild(db)
    assert db.execute("select count(*) from lots where estimated").fetchone()[0] == 0
