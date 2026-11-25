import re
from pathlib import Path

import pytest

from fake_worker import KEY, FakeWorker
from stockpilot import store
from stockpilot.sources import kite

ROOT = Path(__file__).parents[2]

PAYLOAD = {
    "fetched_at": "2026-11-23T09:10:00Z",
    "holdings": [
        {"tradingsymbol": "SBIN", "exchange": "NSE", "isin": "INE062A01020", "quantity": 10, "t1_quantity": 2, "average_price": 600.5},
        {"tradingsymbol": "TCS", "exchange": "NSE", "isin": "INE467B01029", "quantity": 5, "t1_quantity": 0, "average_price": 3500},
    ],
    "mf_holdings": [{"folio": "123", "fund": "Some Fund", "tradingsymbol": "INF000A01010", "average_price": 50.0, "quantity": 100.5}],
    "trades": [{"trade_id": "1"}], "positions": {"net": [], "day": []}, "margins": {"equity": {}}, "gtts": [],
}


@pytest.fixture
def worker():
    w = FakeWorker(kite=PAYLOAD)
    yield w
    w.close()


def client(w):
    return kite.Worker(w.url, KEY)


def add_lot(db, kind, isin, symbol, qty, closed=0):
    db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, closed_quantity) "
               "values (?, ?, ?, '2024-01-01', ?, 100, ?)", [kind, symbol, isin, qty, closed])


def test_sync_writes_a_holdings_snapshot_for_stocks_and_funds(tmp_path, worker):
    db = store.open(tmp_path / "sp.duckdb")
    assert kite.sync(db, client(worker))["holdings"] == 3
    rows = db.execute("select kind, symbol, isin, quantity, avg_price, source from holdings order by symbol").fetchall()
    assert rows == [("mf", "INF000A01010", "INF000A01010", 100.5, 50.0, "kite"),
                    ("stock", "SBIN", "INE062A01020", 12.0, 600.5, "kite"),
                    ("stock", "TCS", "INE467B01029", 5.0, 3500.0, "kite")]
    assert db.execute("select count(*) from kite_syncs").fetchone()[0] == 1
    assert set(worker.seen_keys) == {KEY}


def test_login_needed_is_reported_not_raised_as_a_crash(tmp_path):
    w = FakeWorker(kite=None)
    try:
        db = store.open(tmp_path / "sp.duckdb")
        with pytest.raises(kite.LoginNeeded):
            kite.sync(db, client(w))
        assert db.execute("select count(*) from holdings").fetchone()[0] == 0
    finally:
        w.close()


def test_every_mismatch_against_lots_is_one_problem(tmp_path, worker):
    db = store.open(tmp_path / "sp.duckdb")
    add_lot(db, "stock", "INE062A01020", "SBIN", 11)          # Kite says 12
    add_lot(db, "stock", "INE999Z01010", "OLD", 4)            # Kite has none
    add_lot(db, "stock", "INE467B01029", "TCS", 8, closed=3)  # open 5: matches
    add_lot(db, "rsu", None, "AMZN", 7)                       # not on Kite: ignored
    kite.sync(db, client(worker))                             # fund INF000A01010 has no lot
    rows = db.execute("select key, message from problems where job = 'kite'").fetchall()
    assert len(rows) == 1 and rows[0][0] == "kite-mismatch"
    message = rows[0][1]
    assert message.startswith("Kite and the lots differ for 3 holdings: ")
    assert "SBIN: Kite shows 12." in message and "OLD: Not in Kite." in message and "INF000A01010: No lots for it." in message


def test_only_the_first_five_mismatches_are_named(tmp_path, worker):
    db = store.open(tmp_path / "sp.duckdb")
    for i in range(8):
        add_lot(db, "stock", f"INE00{i}Z01010", f"OLD{i}", 1)
    kite.sync(db, client(worker))
    message = db.execute("select message from problems where key = 'kite-mismatch'").fetchone()[0]
    assert "differ for 11 holdings" in message and "OLD0" in message and "OLD7" not in message
    assert message.count(":") <= 7           # five named, then "and 6 more."


def test_a_clean_match_logs_nothing(tmp_path, worker):
    db = store.open(tmp_path / "sp.duckdb")
    add_lot(db, "stock", "INE062A01020", "SBIN", 12)
    add_lot(db, "stock", "INE467B01029", "TCS", 5)
    add_lot(db, "mf", "INF000A01010", "INF000A01010", 100.5)
    kite.sync(db, client(worker))
    assert db.execute("select count(*) from problems").fetchone()[0] == 0


def test_with_no_lots_yet_one_note_is_logged_not_one_per_holding(tmp_path, worker):
    db = store.open(tmp_path / "sp.duckdb")
    kite.sync(db, client(worker))
    assert db.execute("select count(*) from problems where job = 'kite'").fetchone()[0] == 1


def test_kite_code_only_names_the_read_endpoints():
    allowed = {"/portfolio/holdings", "/mf/holdings", "/trades", "/portfolio/positions", "/user/margins",
               "/gtt/triggers", "/session/token"}
    sources = [ROOT / "src/stockpilot/sources/kite.py", *sorted((ROOT / "web/functions").rglob("*.js")),
               *sorted((ROOT / "web/lib").rglob("*.js"))]
    found = set()
    for src in sources:
        text = src.read_text()
        for m in re.finditer(r"""['"`](/(?:portfolio|mf|trades|user|gtt|session|orders|instruments|quote|margins|ltp|ohlc)[^'"`?\s]*)""", text):
            found.add(m.group(1))
        assert not re.search(r"orders", text, re.I) or "kite" not in src.name.lower(), src
    assert found and found <= allowed, found - allowed
