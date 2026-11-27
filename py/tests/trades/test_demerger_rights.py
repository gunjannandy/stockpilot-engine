"""Lane P1: demergers and rights from NSE, the demerger price factor, base-rate windows, and estimated lots."""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from pytest import approx

from helpers import insert_prices
from stockpilot import store
from stockpilot.analysis import analytics, backtest
from stockpilot.book import units
from stockpilot.trades import corporate_actions as ca, lots

FIXTURE = Path(__file__).parents[1] / "fixtures" / "nse_demerger_rights.json"


def rows():
    return {r["symbol"]: r for r in json.loads(FIXTURE.read_text())}


def weekdays(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def load(db, symbol, days, closes):
    insert_prices(db, [(d, symbol, "NSE", "EQ", c, c, c, c, closes[i - 1] if i else c, 1000, 3e7, 10)
                       for i, (d, c) in enumerate(zip(days, closes))])


# --- parsing -----------------------------------------------------------------------------------------------

def test_a_demerger_row_is_kept_as_a_demerger():
    a = ca.from_nse(rows()["VEDL"])
    assert (a.symbol, a.kind, a.ex_date, a.source) == ("VEDL", "demerger", date(2026, 4, 30), "nse")


def test_a_rights_row_keeps_the_ratio_and_the_price_paid():
    a = ca.from_nse(rows()["BASML"])
    assert (a.kind, a.numerator, a.denominator) == ("rights", 1, 4)
    assert a.price == 55.0            # face value 10 plus premium 45


def test_a_dividend_row_is_still_dropped():
    assert ca.from_nse(rows()["ITC"]) is None


def test_saved_rights_keep_their_price(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    ca.save(db, [ca.from_nse(rows()["BASML"])])
    assert db.execute("select price from action_terms where symbol = 'BASML'").fetchone() == (55.0,)


# --- the demerger price factor -------------------------------------------------------------------------------

def demerger(db, symbol, ex):
    ca.save(db, [ca.Action(symbol, None, ex, "demerger", 1, 1, "Demerger")])


def test_the_factor_is_the_ex_date_jump_and_history_is_adjusted(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    days = weekdays(date(2026, 3, 2), 30)
    load(db, "DEMCO", days, [100.0] * 15 + [70.0] * 15)
    demerger(db, "DEMCO", days[15])
    assert ca.derive_demerger_factors(db) == 1
    assert db.execute("select price_factor from demerger_factors").fetchone()[0] == approx(100 / 70)
    adj = dict(analytics.adjusted_closes(db, "DEMCO", since=days[0]))
    assert [adj[d] for d in days] == approx([70.0] * 30)


def test_a_small_move_is_not_a_demerger_jump(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    days = weekdays(date(2026, 3, 2), 30)
    load(db, "SMALL", days, [100.0] * 15 + [90.0] * 15)       # 11% down: under the 15% line
    demerger(db, "SMALL", days[15])
    assert ca.derive_demerger_factors(db) == 0
    adj = dict(analytics.adjusted_closes(db, "SMALL", since=days[0]))
    assert adj[days[0]] == approx(100.0)


def test_a_split_on_the_same_day_means_no_demerger_factor(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    days = weekdays(date(2026, 3, 2), 30)
    load(db, "BOTH", days, [100.0] * 15 + [50.0] * 15)
    demerger(db, "BOTH", days[15])
    ca.save(db, [ca.Action("BOTH", None, days[15], "split", 2, 1, "Split")])
    assert ca.derive_demerger_factors(db) == 0
    adj = dict(analytics.adjusted_closes(db, "BOTH", since=days[0]))
    assert adj[days[0]] == approx(50.0)                        # only the split applied


def test_ingest_derives_the_factor_and_keeps_it_on_the_next_run(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    days = weekdays(date(2026, 4, 1), 30)
    ex = days[15]
    load(db, "VEDL", days, [100.0] * 15 + [70.0] * 15)
    feed = [{**rows()["VEDL"], "exDate": ex.strftime("%d-%b-%Y")}]
    for _ in range(2):
        ca.ingest(db, ex, lambda path: feed)
        assert db.execute("select price_factor from demerger_factors").fetchone()[0] == approx(100 / 70)


# --- base rates skip the 20 trading days around a demerger ---------------------------------------------------

START = date(2024, 1, 1)


def _series(symbol, days=420):
    return [(START + timedelta(i), symbol, "NSE", "EQ", 100 * 1.002 ** i, 0, 0, 100 * 1.002 ** i,
             100 * 1.002 ** max(i - 1, 0), 1000, 3e7, 10) for i in range(days)]


def _rates(db):
    for i in range(420):
        db.execute("insert into index_levels values (?, 'Nifty 50', 20000, 20, 3, 1)", [START + timedelta(i)])
    r = backtest.base_rates(db, START + timedelta(260), START + timedelta(380), horizon_days=30, step_days=30, buckets=2)
    return sum(v["n"] for v in r.values())


def test_base_rates_skip_steps_within_20_days_of_a_demerger(tmp_path):
    plain = store.open(tmp_path / "a.duckdb")
    insert_prices(plain, sum((_series(f"S{i}") for i in range(4)), []))
    full = _rates(plain)
    cut = store.open(tmp_path / "b.duckdb")
    insert_prices(cut, sum((_series(f"S{i}") for i in range(4)), []))
    demerger(cut, "S0", START + timedelta(320))                # no price jump: the skip rests on the date alone
    got = _rates(cut)
    assert full - 2 <= got < full            # only S0's steps near the date are lost (one or two steps)


# --- rights do not invent units; Kite's units fill the gap with an estimated lot ----------------------------------

def buy(db, qty, price=100.0, day=date(2025, 1, 10), isin="INE000A01010", symbol="HELD"):
    lots.save_trades(db, [lots.Trade("tradebook", f"t-{day}-{qty}", "stock", symbol, isin, "buy", day, qty, price)])


def kite(db, qty, avg, isin="INE000A01010", symbol="HELD", kind="equity", at=datetime(2026, 11, 24, 9)):
    db.execute("insert into holdings values (?, ?, ?, ?, ?, ?, 'kite')", [at, kind, symbol, isin, qty, avg])


def test_an_nse_rights_row_adds_no_lot_by_itself(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    buy(db, 40)
    ca.save(db, [ca.Action("HELD", "INE000A01010", date(2026, 3, 12), "rights", 1, 4, "Rights 1:4 @ Premium Rs 45/-", price=55.0)])
    lots.rebuild(db)
    assert db.execute("select sum(quantity) from lots").fetchone()[0] == 40


def test_units_kite_has_beyond_the_lots_become_one_estimated_lot(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    buy(db, 40)
    kite(db, 50, 120.0)
    lots.rebuild(db)
    assert units.gaps(db) == []
    est = db.execute("select quantity, cost_per_unit, estimated from lots where estimated").fetchall()
    assert est == [(10.0, 120.0, True)]
    assert db.execute("select count(*) from lots where not estimated").fetchone()[0] == 1


def test_a_holding_with_no_documents_is_wholly_estimated(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    kite(db, 25, 300.0, isin="INE000B01010", symbol="NEWCO")
    lots.rebuild(db)
    assert db.execute("select symbol, quantity, estimated from lots").fetchall() == [("NEWCO", 25.0, True)]
    assert units.gaps(db) == []


def test_a_document_replaces_the_estimated_lot(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    buy(db, 40)
    kite(db, 50, 120.0)
    lots.rebuild(db)
    buy(db, 10, price=110.0, day=date(2026, 3, 12))            # the rights allotment arrives as a document
    lots.rebuild(db)
    assert db.execute("select count(*) from lots where estimated").fetchone()[0] == 0
    assert db.execute("select sum(quantity) from lots").fetchone()[0] == 50
    assert units.gaps(db) == []


def test_documents_beyond_kite_are_left_alone(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    buy(db, 40)
    kite(db, 30, 100.0)
    lots.rebuild(db)
    assert db.execute("select count(*) from lots where estimated").fetchone()[0] == 0


def test_no_kite_snapshot_means_no_estimate(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    buy(db, 40)
    lots.rebuild(db)
    assert db.execute("select count(*) from lots where estimated").fetchone()[0] == 0


def test_the_portfolio_says_the_units_are_estimated(tmp_path):
    from stockpilot.book import positions
    db = store.open(tmp_path / "sp.duckdb")
    buy(db, 40)
    kite(db, 50, 120.0)
    lots.rebuild(db)
    p = next(p for p in positions.held(db, date(2026, 11, 24)) if p.isin == "INE000A01010")
    assert p.quantity == 50 and "estimated" in (p.check or "").lower()
