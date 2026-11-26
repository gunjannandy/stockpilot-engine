"""One tick, end to end on a fake Machine: the queue first, then the one job that is due; the database is closed while the
runner and wrangler work; a late NSE and a failing runner are retried by later ticks, within their caps."""
import json
from datetime import datetime

import pytest

from fake_worker import KEY, FakeWorker
from fakes import make_machine, settle, without_bhavcopy
from helpers import hold_lock
from fake_model import item
from test_jobs import fetch

no_bhavcopy = without_bhavcopy(fetch)

from stockpilot import cli, store

from stockpilot.sources import kite
from stockpilot.jobs import daily, due, tick
from stockpilot.calls.runner import RunnerError

FRIDAY = datetime(2026, 11, 20)
SATURDAY = datetime(2026, 11, 21)


def at(day, hour, minute=3):
    return day.replace(hour=hour, minute=minute)


def analyst(m, seen=None, fail=False):
    """A fake runner that notes whether the writer lock was free while it ran."""
    def analyse(brief, role, runners, **kw):
        m.log.append(("runner", role, store.holder(m.db_path)))
        if fail:
            raise RunnerError("the runner is down")
        return {"runner": "fake", "failures": [],
                "decisions": {"market_view": "Calm.", "items": [item(s["symbol"], 0.5) for s in brief["stocks"]]}}
    return analyse


def evening(tmp_path, now=at(FRIDAY, 19), **kw):
    m = make_machine(tmp_path, now=now, **kw)
    m.analyse = analyst(m, fail=kw.get("fail", False)) if "analyse" not in kw else kw["analyse"]
    return m


def go(m):
    """One tick, then the run rows are dated by the fake clock."""
    report = tick.run(m)
    settle(m)
    return report


def full_evening(m, hour=19):
    """The two ticks of a normal evening: gather everything, then (the required sources in, after 19:00) the crunch."""
    m.clock.now = at(FRIDAY, hour, 3)
    first = go(m)
    m.clock.now = at(FRIDAY, hour, 13)
    return {**first, **go(m)}


def runs(m, job=None):
    with m.db("t") as db:
        q = "select job, status from runs" + (" where job = ?" if job else "") + " order by id"
        return db.execute(q, [job] if job else []).fetchall()


def test_an_evening_gathers_on_one_tick_and_crunches_on_the_next(tmp_path):
    m = evening(tmp_path)
    report = go(m)
    assert list(report) == ["queue", "gather"] and report["gather"]["status"] == "ok" and tick.exit_code(report) == 0
    m.clock.now = at(FRIDAY, 19, 13)
    report = go(m)
    assert list(report) == ["queue", "crunch"] and report["crunch"]["status"] == "ok" and tick.exit_code(report) == 0
    assert [j for j, _ in runs(m)] == ["queue", "daily_ingest", "kite", "queue", "crunch", "daily_decide"]
    assert [x for x in m.log if isinstance(x, str)] == ["push_status", "deploy"]


def test_the_runner_and_wrangler_run_with_the_database_closed(tmp_path):
    seen = []
    m = evening(tmp_path)
    m.deploy = lambda: seen.append(("deploy", store.holder(m.db_path))) or "Dashboard deployed."
    m.push_status = lambda status: seen.append(("status", store.holder(m.db_path)))
    full_evening(m)
    runner = [h for kind, role, h in (x for x in m.log if isinstance(x, tuple))]
    assert runner == [None]                                   # one analyst call, the lock free
    assert seen == [("status", None), ("deploy", None)]


def test_the_network_fetches_run_with_the_database_closed(tmp_path):
    held = []

    def watching(url):
        held.append(store.holder(m.db_path))
        return fetch(url)
    m = evening(tmp_path, fetch=watching)
    go(m)
    assert held and all(h is None for h in held)


def test_a_late_nse_is_retried_every_tick_and_the_rest_is_stored_then_one_problem_after_23_00(tmp_path):
    m = evening(tmp_path, fetch=no_bhavcopy)
    for hour, minute in ((16, 3), (19, 3), (21, 3)):
        m.clock.now = at(FRIDAY, hour, minute)
        report = go(m)
        assert report["gather"]["status"] == "waiting" and tick.exit_code(report) == 75
    with m.db("t") as db:
        assert due.read_state(db, m.clock(), m.root).gathered >= {"bse_prices", "indices", "deals"}   # stored, not blocked
        assert db.execute("select count(*) from runs where job = 'daily_ingest'").fetchone()[0] == 1   # a quiet tick adds no row
    assert not [x for x in m.log if x == "deploy"]            # nothing is shipped while waiting
    for hour, minute in ((23, 3), (23, 13)):
        m.clock.now = at(FRIDAY, hour, minute)
        assert "gather" not in go(m)
    with m.db("t") as db:
        assert db.execute("select count(*), max(message) from problems where key like 'nse-late-%'").fetchone() == (
            1, "NSE did not publish 2026-11-20's prices.")
        assert db.execute("select count(*), max(message) from problems where key like 'gather-missing-%'").fetchone() == (
            1, "Not gathered today (2026-11-20): nse_prices.")             # one grouped row, however many ticks


def test_the_prices_arrive_late_and_the_next_ticks_finish_the_evening(tmp_path):
    state = {"out": True}
    m = evening(tmp_path, fetch=lambda url: no_bhavcopy(url) if state["out"] else fetch(url))
    assert go(m)["gather"]["status"] == "waiting"
    state["out"] = False
    m.clock.now = at(FRIDAY, 20, 13)
    assert go(m)["gather"]["status"] == "ok"
    m.clock.now = at(FRIDAY, 20, 23)
    assert go(m)["crunch"]["status"] == "ok"
    m.clock.now = at(FRIDAY, 20, 33)
    assert not {"gather", "crunch"} & set(go(m))        # the calls exist and every source is in: the evening is over


def test_the_runner_step_runs_at_most_twice_an_evening(tmp_path):
    m = evening(tmp_path, analyse=lambda *a, **k: (_ for _ in ()).throw(RunnerError("down")))
    calls = []
    m.analyse = lambda brief, role, runners, **kw: calls.append(role) or (_ for _ in ()).throw(RunnerError("down"))
    for minute in (3, 13, 23, 33, 43):
        m.clock.now = at(FRIDAY, 19, minute)
        go(m)
    assert calls == ["analyst", "analyst"]
    assert [s for j, s in runs(m) if j == "daily_decide"] == ["failed", "failed"]
    assert [s for j, s in runs(m) if j == "daily_ingest"] == ["ok"]      # the retry did not fetch again


def test_one_job_per_tick_and_the_queue_always_first(tmp_path):
    w = FakeWorker(kite=None, queue=[{"id": "001", "kind": "budget_set", "payload": {"month": "2026-12", "amount": 5},
                                      "by": "father", "at": "x"}])
    try:
        m = evening(tmp_path, worker=kite.Worker(w.url, KEY))
        report = go(m)
    finally:
        w.close()
    assert list(report) == ["queue", "gather"] and report["queue"] == {"done": 1, "failed": 0}
    with m.db("t") as db:
        assert db.execute("select amount_inr from budgets").fetchone()[0] == 5


def test_a_rerun_asked_for_at_noon_runs_the_whole_job_again_and_the_file_is_taken(tmp_path):
    m = evening(tmp_path)
    full_evening(m)
    m.clock.now = at(FRIDAY, 22, 3)
    assert not {"daily", "crunch"} & set(go(m))
    due.ask_rerun(tmp_path, "daily")
    m.clock.now = at(FRIDAY, 22, 13)
    assert go(m)["daily"]["status"] == "ok"
    assert due.pending_reruns(tmp_path) == frozenset()
    assert [s for j, s in runs(m) if j == "daily_ingest"] == ["ok", "ok"]
    assert "daily" not in go(m)


def test_a_job_that_raises_is_a_problem_and_the_tick_goes_on(tmp_path):
    m = evening(tmp_path)
    m.deploy = lambda: (_ for _ in ()).throw(RuntimeError("wrangler exited 1"))
    report = full_evening(m)
    assert report["crunch"]["status"] == "ok"                  # a failed deploy is a problem row, not a failed evening
    with m.db("t") as db:
        assert db.execute("select count(*) from problems where job = 'deploy'").fetchone()[0] == 1


def test_a_tick_that_meets_a_busy_database_is_skipped_and_exits_75(tmp_path, monkeypatch):
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    (root / "config" / "stockpilot.yaml").write_text("store:\n  path: data/sp.duckdb\n")
    m = make_machine(root, now=at(FRIDAY, 19))
    m.wait_s = 0.2
    monkeypatch.setattr(cli, "_machine", lambda cfg, job="tick": m)
    proc = hold_lock(root / "data" / "sp.duckdb", 30)
    try:
        assert cli.main(["--root", str(root), "tick"]) == 75
    finally:
        proc.kill()
        proc.wait()
    assert json.loads((root / "data" / "skipped.jsonl").read_text().splitlines()[0])["job"] == "tick"


def test_cli_tick_exits_75_while_waiting_and_0_when_the_evening_is_done(tmp_path, monkeypatch):
    m = evening(tmp_path, fetch=no_bhavcopy)
    monkeypatch.setattr(cli, "_machine", lambda cfg, job="tick": m)
    assert cli.main(["--root", str(tmp_path), "tick"]) == 75
    m.fetch = fetch
    m.clock.now = at(FRIDAY, 19, 13)
    assert cli.main(["--root", str(tmp_path), "tick"]) == 0


def test_a_rerun_pressed_on_the_dashboard_runs_in_the_same_tick(tmp_path):
    w = FakeWorker(kite=None, queue=[{"id": "001", "kind": "rerun", "payload": {"job": "nav"}, "by": "father", "at": "x"}])
    try:
        m = evening(tmp_path, now=at(FRIDAY, 12), worker=kite.Worker(w.url, KEY))
        m.analyse = None
        report = go(m)
    finally:
        w.close()
    assert list(report) == ["queue", "nav"] and report["queue"] == {"done": 1, "failed": 0}
    assert due.pending_reruns(tmp_path) == frozenset()


def test_a_failing_kite_read_is_tried_at_most_three_times_an_evening_then_reported(tmp_path, monkeypatch):
    """Issue #5: not every ten minutes until 23:00. After the third failure the owners are told, in plain words."""
    def broken(worker):
        raise RuntimeError("Worker /api/vm/kite answered 502")
    monkeypatch.setattr(kite, "fetch", broken)
    m = evening(tmp_path, worker=object())
    for minute in range(3, 60, 10):                      # six ticks of the 19:00 hour
        m.clock.now = at(FRIDAY, 19, minute)
        daily.gather(m, m.clock.now)
        settle(m)
    assert [s for _, s in runs(m, "kite")] == ["failed"] * due.KITE_MAX
    with m.db("t") as db:
        notes = [r[0] for r in db.execute("select message from problems where message like '%Kite%'").fetchall()]
    assert any("3 tries" in n and "Sync now" in n for n in notes)
    m.clock.now = at(FRIDAY, 21, 3)
    daily.gather(m, m.clock.now)
    assert len(runs(m, "kite")) == due.KITE_MAX          # later evening ticks do not try again


def test_a_login_needed_kite_read_is_one_try_and_not_a_failure(tmp_path, monkeypatch):
    w = FakeWorker(kite=None)
    try:
        m = evening(tmp_path, worker=kite.Worker(w.url, KEY))
        for minute in (3, 13, 23):
            m.clock.now = at(FRIDAY, 19, minute)
            daily.gather(m, m.clock.now)
            settle(m)
    finally:
        w.close()
    assert [s for _, s in runs(m, "kite")] == ["ok"]
