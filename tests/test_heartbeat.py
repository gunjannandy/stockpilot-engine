"""A busy database does not silence the status: the doctor pushes a heartbeat, and the watchdog trusts a fresh one."""
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

from helpers import hold_lock
from stockpilot import cli, ops
from stockpilot.jobs import doctor

ROOT = Path(__file__).parent.parent


@pytest.fixture
def root(tmp_path):
    r = tmp_path / "proj"
    (r / "config").mkdir(parents=True)
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=r, check=True)
    (r / "config" / "stockpilot.yaml").write_text("store:\n  path: data/sp.duckdb\nvault:\n  remote: origin\n")
    return r


def _pushed(root):
    bare = root.parent / "remote.git"
    out = subprocess.run(["git", "--git-dir", str(bare), "show", "status:status.json"], capture_output=True, text=True)
    return json.loads(out.stdout) if out.returncode == 0 else None


def test_heartbeat_is_built_without_the_database():
    holder = {"job": "daily", "pid": 7, "since": "2026-11-23T13:30:00+00:00"}
    beat = doctor.heartbeat(holder, datetime(2026, 11, 23, 20, 17))
    assert beat["busy"] == holder and beat["ok"] is None
    assert datetime.fromisoformat(beat["generated_at"]).tzinfo is not None
    assert set(beat) == {"generated_at", "busy", "ok"}


def test_a_busy_doctor_still_pushes_a_heartbeat(root):
    proc = hold_lock(root / "data" / "sp.duckdb", 60)
    try:
        assert cli.main(["--root", str(root), "doctor"]) == 0
    finally:
        proc.kill()
        proc.wait()
    status = _pushed(root)
    assert status["ok"] is None and status["busy"]["job"] == "holder-job" and status["busy"]["pid"] == proc.pid
    assert "findings" not in status
    skipped = (root / "data" / "skipped.jsonl").read_text()
    assert json.loads(skipped.splitlines()[0])["job"] == "doctor"


def test_a_busy_doctor_with_no_push_pushes_nothing(root):
    proc = hold_lock(root / "data" / "sp.duckdb", 60)
    try:
        assert cli.main(["--root", str(root), "doctor", "--no-push"]) == 0
    finally:
        proc.kill()
        proc.wait()
    assert _pushed(root) is None


def test_the_watchdog_trusts_a_fresh_busy_status():
    sys.path.insert(0, str(ROOT / "ops"))
    import watchdog
    now = datetime.fromisoformat("2026-11-20T15:30:00+00:00")       # a Friday, 21:00 IST
    busy = {"generated_at": "2026-11-20T14:30:00+00:00", "busy": {"job": "daily"}, "ok": None}
    assert watchdog.verdict(busy, now) == "ok"
    assert watchdog.verdict({**busy, "generated_at": "2026-11-20T12:00:00+00:00"}, now) == "reset"   # busy for 3.5 h of silence


def test_the_watchdog_runs_twice_a_day():
    import yaml
    dog = yaml.safe_load((ROOT / ".github" / "workflows" / "watchdog.yml").read_text())
    crons = [s["cron"] for s in dog[True]["schedule"]]
    assert "30 15 * * *" in crons and "0 13 * * *" in crons        # 21:00 and 18:30 IST
