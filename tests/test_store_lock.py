"""The writer lock: one process writes the database at a time; the others wait their turn or say who holds it."""
import json
import time

import pytest

from helpers import hold_lock as _hold
from stockpilot import store

def test_second_process_gets_busy_with_the_holder(tmp_path):
    path = tmp_path / "data" / "sp.duckdb"
    proc = _hold(path, 30)
    try:
        with pytest.raises(store.Busy) as err:
            store.open(path, job="queue")
        assert err.value.holder["job"] == "holder-job"
        assert err.value.holder["pid"] == proc.pid
        assert "since" in err.value.holder
        assert store.holder(path)["job"] == "holder-job"
    finally:
        proc.kill()
        proc.wait()


def test_wait_succeeds_when_the_holder_exits(tmp_path):
    path = tmp_path / "sp.duckdb"
    proc = _hold(path, 1.5)
    try:
        started = time.monotonic()
        db = store.open(path, job="daily", wait_s=20, poll_s=0.2)
        assert 0.5 < time.monotonic() - started < 15
        assert store.holder(path)["job"] == "daily"
        store.close(db)
    finally:
        proc.kill()
        proc.wait()


def test_busy_past_the_wait_raises(tmp_path):
    path = tmp_path / "sp.duckdb"
    proc = _hold(path, 30)
    try:
        started = time.monotonic()
        with pytest.raises(store.Busy):
            store.open(path, wait_s=0.6, poll_s=0.2)
        assert time.monotonic() - started >= 0.5
    finally:
        proc.kill()
        proc.wait()


def test_a_killed_holder_leaves_no_lock(tmp_path):
    path = tmp_path / "sp.duckdb"
    proc = _hold(path, 30)
    proc.kill()
    proc.wait()
    assert store.holder(path) is None      # the file may still say who; nobody holds the lock
    store.close(store.open(path))


def test_holder_without_a_lock_file_is_none(tmp_path):
    assert store.holder(tmp_path / "nothing.duckdb") is None


def test_close_releases_the_lock_and_records_the_holder(tmp_path):
    path = tmp_path / "sp.duckdb"
    db = store.open(path, job="nav")
    held = store.holder(path)
    assert held["job"] == "nav" and held["pid"] > 0
    assert json.loads((tmp_path / "db.lock").read_text())["job"] == "nav"
    store.close(db)
    assert store.holder(path) is None


def test_plain_close_on_the_connection_also_releases(tmp_path):
    path = tmp_path / "sp.duckdb"
    db = store.open(path)
    db.close()
    assert store.holder(path) is None


def test_connection_limits(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert db.execute("select current_setting('threads')").fetchone()[0] == 2
    assert db.execute("select current_setting('memory_limit')").fetchone()[0].startswith("244.")   # 256MB, shown in MiB
    assert db.execute("select current_setting('temp_directory')").fetchone()[0] == str(tmp_path / "tmp")
    assert db.execute("select current_setting('preserve_insertion_order')").fetchone()[0] is False
    store.close(db)


def test_the_screen_jobs_get_a_bigger_limit(tmp_path):
    """Found on the VM: the whole-market screen ran out of memory at 237 of 244 MiB."""
    for job, starts in (("daily", "400."), ("site", "400."), ("queue", "244.")):
        db = store.open(tmp_path / f"{job}.duckdb", job=job)
        assert db.execute("select current_setting('memory_limit')").fetchone()[0].startswith(starts)
        store.close(db)
