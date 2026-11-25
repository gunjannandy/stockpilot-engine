"""The fire drill (brief stage 8): `sp doctor --drill` plants a fault in a scratch copy, and the doctor must open a self-heal
issue that says the cause in plain English; the Rerun request must become a file that the tick takes and acts on."""
import os

import pytest

from stockpilot import cli, store
from stockpilot.jobs import doctor, due

STEPS = ["scratch copy", "fault seen", "issue opened", "plain cause", "no second issue", "rerun file", "tick takes it"]


def _by_step(results):
    return {r["step"]: r for r in results}


def test_the_drill_passes_every_step_and_names_them(tmp_path):
    results = doctor.drill(tmp_path)
    assert [r["step"] for r in results] == STEPS
    assert all(r["ok"] for r in results), [r for r in results if not r["ok"]]


def test_the_drill_never_opens_or_changes_the_live_store(tmp_path):
    live = tmp_path / "data" / "sp.duckdb"
    db = store.open(live)
    db.execute("insert into problems (job, severity, message) values ('live', 'error', 'real')")
    db.close()
    before = (live.stat().st_mtime_ns, live.stat().st_size)
    results = doctor.drill(tmp_path, live_db=live)
    assert all(r["ok"] for r in results)
    assert (live.stat().st_mtime_ns, live.stat().st_size) == before
    assert not (tmp_path / "data" / "rerun").exists()             # the rerun file was written in the scratch folder only


def test_the_drill_fails_the_step_when_the_scratch_is_the_live_store(tmp_path):
    live2 = tmp_path / "data" / "sp.duckdb"
    results = doctor.drill(tmp_path, live_db=live2, scratch=tmp_path)
    assert not _by_step(results)["scratch copy"]["ok"]
    assert not live2.exists()                                      # and nothing was planted


def test_no_issue_means_the_issue_step_fails_and_later_steps_say_why(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "doctor", lambda *a, **k: 0)
    got = _by_step(doctor.drill(tmp_path))
    assert got["fault seen"]["ok"] and not got["issue opened"]["ok"]
    assert not got["plain cause"]["ok"] and not got["rerun file"]["ok"] and not got["tick takes it"]["ok"]


def test_an_issue_without_the_cause_fails_the_plain_cause_step(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "_issue_body", lambda finding, db: f"job: daily_ingest\n{finding['summary']}")
    got = _by_step(doctor.drill(tmp_path))
    assert got["issue opened"]["ok"] and not got["plain cause"]["ok"]
    assert got["rerun file"]["ok"]                                  # the rest still ran


def test_a_second_pass_that_files_again_fails_the_no_second_issue_step(tmp_path, monkeypatch):
    real = doctor.doctor

    def forgetful(db, cfg, now, root, gh):
        db.execute("delete from problems where job = 'doctor'")
        return real(db, cfg, now, root, gh)
    monkeypatch.setattr(doctor, "doctor", forgetful)
    # the fake gh remembers the open issue, so a doctor that forgot its own rows must still not file twice
    assert _by_step(doctor.drill(tmp_path))["no second issue"]["ok"]


def test_no_rerun_file_fails_the_rerun_step(tmp_path, monkeypatch):
    monkeypatch.setattr(doctor, "request_rerun", lambda m, job: 0)
    got = _by_step(doctor.drill(tmp_path))
    assert not got["rerun file"]["ok"] and not got["tick takes it"]["ok"]


def test_a_tick_that_leaves_the_file_fails_the_last_step(tmp_path, monkeypatch):
    monkeypatch.setattr(due, "take_rerun", lambda root, job: None)
    got = _by_step(doctor.drill(tmp_path))
    assert got["rerun file"]["ok"] and not got["tick takes it"]["ok"]


def test_the_command_prints_pass_or_fail_per_step_and_exits_zero(tmp_path, capsys):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "stockpilot.yaml").write_text("store:\n  path: data/sp.duckdb\n")
    assert cli.main(["--root", str(tmp_path), "doctor", "--drill"]) == 0
    out = capsys.readouterr().out
    for step in STEPS:
        assert f"PASS  {step}" in out
    assert not os.path.exists(tmp_path / "data" / "sp.duckdb")        # not even created


def test_the_command_exits_one_when_a_step_fails(tmp_path, capsys, monkeypatch):
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "stockpilot.yaml").write_text("store:\n  path: data/sp.duckdb\n")
    monkeypatch.setattr(doctor, "doctor", lambda *a, **k: 0)
    assert cli.main(["--root", str(tmp_path), "doctor", "--drill"]) == 1
    assert "FAIL  issue opened" in capsys.readouterr().out
