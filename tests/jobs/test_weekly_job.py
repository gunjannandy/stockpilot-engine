"""The Saturday job: refreshes in steps, the slow ones in batches that each end a tick; NAVs fetched lately are skipped."""
from datetime import datetime, timedelta

import pytest

from fakes import make_machine, settle
from stockpilot import store
from stockpilot.jobs import tick, weekly

SATURDAY = datetime(2026, 11, 21)


def at(hour, minute=3):
    return SATURDAY.replace(hour=hour, minute=minute)


def go(m):
    report = tick.run(m)
    settle(m)
    return report


@pytest.fixture
def quiet(monkeypatch):
    """Nothing to fetch except what a test turns on."""
    monkeypatch.setattr("stockpilot.sources.funds.ingest_navall", lambda db, f: 0)
    monkeypatch.setattr("stockpilot.sources.fundamentals.pool", lambda *a: [])


def test_fundamentals_run_in_batches_of_200_that_each_end_a_tick(tmp_path, monkeypatch, quiet):
    names = [f"S{i:03d}" for i in range(450)]
    monkeypatch.setattr("stockpilot.sources.fundamentals.pool", lambda *a: names)
    monkeypatch.setattr("stockpilot.sources.filings.symbols_to_load", lambda *a: [])
    held, fetched = [], []
    m = make_machine(tmp_path, now=at(10))
    m.yahoo = lambda symbol: held.append(store.holder(m.db_path)) or fetched.append(symbol)
    statuses = []
    for minute in (3, 13, 23):
        m.clock.now = at(10, minute)
        report = go(m)
        statuses.append((report["weekly"]["status"], len(fetched)))
        assert list(report) == ["queue", "weekly"]                       # the queue ran between the batches
    assert statuses == [("more", 200), ("more", 400), ("ok", 450)]
    assert fetched == names and set(held) == {None}                      # every symbol once; the lock free for each call
    with m.db("t") as db:
        assert db.execute("select period from fetch_log where source like 'weekly:2026-11-21:fundamentals'").fetchone() == ("done",)
        assert db.execute("select status from runs where job = 'weekly'").fetchall() == [("ok",)]


def test_a_finished_weekly_is_not_due_again(tmp_path, quiet):
    m = make_machine(tmp_path, now=at(10))
    assert go(m)["weekly"]["status"] == "ok"
    m.clock.now = at(10, 13)
    assert "weekly" not in go(m)


def test_navs_fetched_in_the_last_24_hours_are_not_fetched_again(tmp_path, monkeypatch):
    monkeypatch.setattr("stockpilot.sources.fundamentals.pool", lambda *a: [])
    fetched = []
    monkeypatch.setattr("stockpilot.sources.funds.ingest_navall", lambda db, f: fetched.append(1) or 0)
    m = make_machine(tmp_path, now=at(10))
    with m.db("t") as db:
        db.execute("insert into runs (job, started_at, status) values ('nav', ?, 'ok')", [at(10) - timedelta(hours=11)])
    weekly.run(m, at(10))
    assert fetched == []
    m2 = make_machine(tmp_path / "other", now=at(10))
    with m2.db("t") as db:
        db.execute("insert into runs (job, started_at, status) values ('nav', ?, 'ok')", [at(10) - timedelta(hours=30)])
    weekly.run(m2, at(10))
    assert fetched == [1]


def test_filings_are_refreshed_for_the_batch_with_the_lock_free(tmp_path, monkeypatch, quiet):
    monkeypatch.setattr("stockpilot.sources.filings.symbols_to_load", lambda *a: ["AAA", "BBB"])
    seen = []
    m = make_machine(tmp_path, now=at(10), fetch_json=lambda path: seen.append(("json", store.holder(m.db_path))) or {})
    monkeypatch.setattr("stockpilot.sources.filings.refresh",
                        lambda db, fj, ff, symbols, today: seen.append((list(symbols), today, fj("/x"))) or
                        {"stored": 0, "companies": 0})
    weekly.run(m, at(10))
    assert [s for s in seen if isinstance(s[0], list)] == [(["AAA", "BBB"], SATURDAY.date(), {})]
    assert ("json", None) in seen


class MailBridge:
    stale = ""

    def __init__(self, n):
        self.items = [{"id": f"m{i}", "source": "gmail", "subject": "Payment success", "attachments": [], "modified": ""}
                      for i in range(n)]

    def list(self, since=None):
        return self.items


def test_document_sync_works_in_batches_and_the_window_moves_only_at_the_end(tmp_path, monkeypatch, quiet):
    monkeypatch.setattr(weekly, "BATCH", 2)
    m = make_machine(tmp_path, now=at(10), bridge=lambda: (MailBridge(5), "PAN"))
    states = []
    for minute in (3, 13, 23):
        m.clock.now = at(10, minute)
        states.append(go(m)["weekly"]["status"])
        with m.db("t") as db:
            states.append((db.execute("select count(*) from documents").fetchone()[0],
                           db.execute("select count(*) from fetch_log where source = 'docs'").fetchone()[0]))
    assert states == ["more", (2, 0), "more", (4, 0), "ok", (5, 1)]


def test_a_failing_step_is_a_problem_and_the_analysis_still_runs(tmp_path, quiet):
    m = make_machine(tmp_path, now=at(10), bridge=lambda: (_ for _ in ()).throw(ConnectionError("bridge down")))
    assert go(m)["weekly"]["status"] == "ok"
    with m.db("t") as db:
        assert "document sync skipped" in db.execute("select message from problems where job = 'weekly'").fetchone()[0]


def test_a_rerun_starts_the_steps_again(tmp_path, quiet):
    m = make_machine(tmp_path, now=at(10))
    go(m)
    from stockpilot.jobs import due
    due.ask_rerun(tmp_path, "weekly")
    m.clock.now = at(12)
    assert go(m)["weekly"]["status"] == "ok"
    with m.db("t") as db:
        assert db.execute("select count(*) from runs where job = 'weekly'").fetchone()[0] == 2
