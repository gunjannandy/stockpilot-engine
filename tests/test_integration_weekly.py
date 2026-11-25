"""Seams 6 and 7: the weekly pipeline syncs documents and projects RSU vests before tax; every job leaves a runs row."""
import json
from datetime import date, datetime
from types import SimpleNamespace

from test_integration_queue import Bridge
from test_integration_daily import cfg_in, KITE

from fake_worker import KEY, FakeWorker
from fakes import make_machine
from stockpilot import journal, ops, site, store, vmqueue, weekly
from stockpilot.sources import kite
from stockpilot.jobs import daily, docs, due, queue
from stockpilot.jobs import weekly as weekly_job
from stockpilot.trades import lots

SAT = date(2026, 11, 21)


def vest(db, on, qty):
    lots.save_trades(db, [lots.Trade("fidelity", f"v{on}", "rsu", "NOW", "US81762P1021", "vest", on, qty, 800.0,
                                     currency="USD")])


def test_weekly_projects_the_next_vests_and_the_tax_section_lists_them(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    vest(db, date(2026, 8, 15), 10)
    weekly.run(db, SAT, tmp_path / "pack")
    rows = db.execute("select trade_date, quantity, status from trades where status = 'expected' order by 1").fetchall()
    # one a quarter, up to six months ahead; the first is already past due and still unconfirmed
    assert rows == [(date(2026, 11, 15), 10.0, "expected"), (date(2027, 2, 15), 10.0, "expected"),
                    (date(2027, 5, 15), 10.0, "expected")]
    tax = json.loads(db.execute("select payload from weekly_reports where section = 'tax'").fetchone()[0])
    assert tax["expected_vests"][0]["quantity"] == 10
    notes = site.weekly_view(db, "tax")["notes"]
    assert any("was due around 2026-11-15" in n and "Not counted" in n for n in notes)
    lots.rebuild(db)
    assert db.execute("select count(*) from lots").fetchone()[0] == 1      # the projection never becomes a lot
    weekly.run(db, SAT, tmp_path / "pack")
    assert db.execute("select count(*) from trades where status = 'expected'").fetchone()[0] == 3   # replaced, not piled up


def _weekly_all(m, now):
    out = {"status": "more"}
    while out["status"] == "more":
        out = weekly_job.run(m, now)
    return out


def test_weekly_syncs_documents_before_the_analysis_and_skips_it_when_analyse_only(tmp_path, monkeypatch):
    m = make_machine(tmp_path, bridge=lambda: (Bridge(), "PAN"))
    log = []
    monkeypatch.setattr("stockpilot.sources.funds.ingest_navall", lambda db, f: log.append("navs"))
    monkeypatch.setattr("stockpilot.sources.fundamentals.pool", lambda *a: [])
    real_sync = docs.sync_batch
    monkeypatch.setattr(docs, "sync_batch", lambda *a, **k: log.append("sync") or real_sync(*a, **k))
    real_run = weekly.run
    monkeypatch.setattr(weekly, "run", lambda *a, **k: log.append("weekly") or real_run(*a, **k))
    assert _weekly_all(m, datetime(2026, 11, 21, 12))["status"] == "ok"
    assert log == ["navs", "sync", "weekly"]
    with m.db("t") as db:
        assert db.execute("select count(*) from trades").fetchone()[0] == 6       # the Drive tradebook came through
    log.clear()
    assert weekly_job.run(m, datetime(2026, 11, 21, 12), analyse_only=True)["status"] == "ok"
    assert log == ["weekly"]


def test_a_missing_bridge_secret_is_a_warning_and_the_weekly_still_runs(tmp_path, monkeypatch):
    from stockpilot import config
    m = make_machine(tmp_path, bridge=lambda: docs.bridge_from(m.cfg))
    for name in ("GOOGLE_BRIDGE_URL", "GOOGLE_BRIDGE_KEY", "OWNER_PAN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr("stockpilot.sources.funds.ingest_navall", lambda db, f: 0)
    monkeypatch.setattr("stockpilot.sources.fundamentals.pool", lambda *a: [])
    assert _weekly_all(m, datetime(2026, 11, 21, 12))["status"] == "ok"
    with m.db("t") as db:
        assert "document sync skipped" in db.execute("select message from problems where job = 'weekly'").fetchone()[0]


# ---- seam 7: runs rows --------------------------------------------------------------------------

def test_tracked_writes_a_run_row_and_a_failure_is_recorded_and_raised(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert journal.tracked(db, "nav", lambda: {"navs": 3}) == {"navs": 3}
    try:
        journal.tracked(db, "queue", lambda: 1 / 0)
    except ZeroDivisionError:
        pass
    assert db.execute("select job, status from runs order by id").fetchall() == [("nav", "ok"), ("queue", "failed")]


def test_queue_and_kite_leave_run_rows_and_the_doctor_watches_them(tmp_path):
    w = FakeWorker(kite=KITE, queue=[{"id": "001", "kind": "rerun", "payload": {}, "by": "father", "at": "x"}])
    try:
        m = make_machine(tmp_path, worker=kite.Worker(w.url, KEY), extra="freshness: {queue: 12, kite: 36}\n")
        with m.db("kite") as db:
            assert daily.run_kite(db, m.worker)["status"] == "ok"
        queue.run(m)
    finally:
        w.close()
    assert due.pending_reruns(tmp_path) == {"daily"}          # the rerun waits for the tick that is running
    with m.db("t") as db:
        assert set(db.execute("select job from runs where status = 'ok'").fetchall()) == {("kite",), ("queue",)}
        now = datetime.now()
        assert not [f for f in ops.diagnose(db, {"freshness": {"queue": 12, "kite": 36, "nav": 30}}, now, tmp_path)
                    if f["key"] in ("queue-stale", "kite-stale")]
        stale = ops.diagnose(db, {"freshness": {"nav": 30}}, now, tmp_path)
        assert any(f["key"] == "nav-stale" for f in stale)
