"""Reruns work: the doctor lets go of the database first, then starts the job's systemd unit (or a subprocess)."""
import json
import os
import subprocess
import sys

import pytest

from stockpilot import machine, ops, store
from stockpilot.jobs import doctor, due

GH = f"""#!{sys.executable}
import json, sys
args = sys.argv[1:]
if args[:2] == ["issue", "list"] and "rerun-requested" in args:
    print(json.dumps([{{"number": 9, "body": "job: daily_ingest\\nkey: daily_ingest-stale", "labels": []}}]))
elif args[:2] == ["issue", "list"]:
    print("[]")
"""

# a fake `sudo`: records whether the database lock was free at the moment the unit was started
SUDO = f"""#!{sys.executable}
import sys
from stockpilot import store
free = store.holder(sys.argv[1]) is None
open(sys.argv[2], "a").write(("free " if free else "held ") + " ".join(sys.argv[3:]) + "\\n")
"""


def test_the_doctor_closes_the_database_before_it_starts_the_unit(tmp_path):
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    (root / "config" / "stockpilot.yaml").write_text("store:\n  path: data/sp.duckdb\n")
    store.close(store.open(root / "data" / "sp.duckdb"))
    bin_dir, log = tmp_path / "bin", tmp_path / "sudo.log"
    bin_dir.mkdir()
    (bin_dir / "gh").write_text(GH)
    # the wrapper hands the db path and the log to the fake sudo
    (bin_dir / "sudo").write_text(f'#!/bin/sh\nexec {sys.executable} {tmp_path / "sudo.py"} "{root / "data" / "sp.duckdb"}" "{log}" "$@"\n')
    (tmp_path / "sudo.py").write_text(SUDO.split("\n", 1)[1])
    for f in ("gh", "sudo"):
        (bin_dir / f).chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    out = subprocess.run([sys.executable, "-m", "stockpilot.cli", "--root", str(root), "doctor", "--no-push"],
                         env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert log.read_text().strip() == "free -n systemctl start --no-block sp-tick.service"
    assert (root / "data" / "rerun" / "daily").exists()          # the tick finds what to run in this file


def test_a_failing_systemctl_falls_back_to_a_tick_subprocess(tmp_path):
    ran, started = [], []

    def run(argv, **kw):
        ran.append(argv)
        return subprocess.CompletedProcess(argv, 1)

    machine.start_tick(tmp_path, run=run, popen=lambda argv, **kw: started.append(argv))
    assert ran[0] == ["sudo", "-n", "systemctl", "start", "--no-block", "sp-tick.service"]
    assert started[0][1:3] == ["-m", "stockpilot.cli"] and started[0][-1] == "tick"


def test_no_sudo_at_all_also_falls_back(tmp_path):
    started = []

    def run(argv, **kw):
        raise FileNotFoundError("sudo")

    machine.start_tick(tmp_path, run=run, popen=lambda argv, **kw: started.append(argv))
    assert len(started) == 1


def test_a_started_unit_is_not_run_a_second_time(tmp_path):
    started = []
    machine.start_tick(tmp_path, run=lambda argv, **kw: subprocess.CompletedProcess(argv, 0),
                       popen=lambda argv, **kw: started.append(argv))
    assert started == []


def test_a_rerun_request_leaves_a_file_and_starts_a_tick(tmp_path):
    from fakes import make_machine
    m = make_machine(tmp_path)
    assert doctor.request_rerun(m, "nav") == 0
    assert m.log == ["start_tick"] and due.pending_reruns(tmp_path) == {"nav"}


def test_queue_is_a_job_the_doctor_can_rerun():
    assert doctor.JOB_OF["queue"] == "queue"
    gh = lambda *a: json.dumps([{"number": 3, "body": "job: queue\nkey: queue-stale", "labels": []}]) if a[:2] == ("issue", "list") else ""
    ran = []
    assert doctor.apply_reruns(gh, lambda job: ran.append(job) or 0) == 1
    assert ran == ["queue"]
