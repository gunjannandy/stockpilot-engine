"""A busy database is recorded: skipped.jsonl while it cannot be opened, a `skipped` run once it can."""
import json

import pytest

from helpers import hold_lock
from stockpilot import cli, journal, store


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "proj"
    (r / "config").mkdir(parents=True)
    (r / "config" / "stockpilot.yaml").write_text("store:\n  path: data/sp.duckdb\n")
    return r


@pytest.fixture
def held(root):
    proc = hold_lock(root / "data" / "sp.duckdb", 60)
    yield proc
    proc.kill()
    proc.wait()


def lines(root):
    path = root / "data" / "skipped.jsonl"
    return [json.loads(l) for l in path.read_text().splitlines()] if path.exists() else []


@pytest.mark.parametrize("command, code", [("queue", 0), ("doctor", 0), ("ship", 75), ("nav", 75), ("score", 75), ("tick", 75)])
def test_busy_command_records_and_exits(root, held, command, code, monkeypatch):
    monkeypatch.setattr(cli, "WAITS", {job: 0.3 for job in cli.WAITS})      # the real waits are minutes
    extra = ["--no-push"] if command == "doctor" else []      # the heartbeat push is tested in test_heartbeat.py
    assert cli.main(["--root", str(root), command, *extra]) == code
    [line] = lines(root)
    assert line["job"] == command
    assert line["holder"]["job"] == "holder-job" and line["holder"]["pid"] == held.pid
    assert line["at"]


def test_skipped_lines_become_runs_on_the_next_open(root, held):
    cli.main(["--root", str(root), "queue"])
    held.kill()
    held.wait()
    db = store.open(root / "data" / "sp.duckdb")
    [(job, status, notes)] = db.execute("select job, status, notes from runs").fetchall()
    assert (job, status) == ("queue", "skipped")
    assert json.loads(notes)["holder"]["job"] == "holder-job"
    assert lines(root) == []                    # moved, not copied
    store.close(db)
    db = store.open(root / "data" / "sp.duckdb")
    assert db.execute("select count(*) from runs").fetchone()[0] == 1      # and not moved twice


def test_waits_per_job(root):
    assert cli.WAITS == {"tick": 5 * 60, "daily": 45 * 60, "ship": 30 * 60, "nav": 30 * 60, "weekly": 60 * 60, "kite": 10 * 60,
                         "queue": 0, "redeploy": 5 * 60, "doctor": 0, "ownership": 30 * 60}


def test_flush_skipped_with_no_file_is_a_no_op(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert journal.flush_skipped(db) == 0
