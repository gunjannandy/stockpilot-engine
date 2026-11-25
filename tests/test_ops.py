"""Ops: scoring, doctor, status, archive, and the planted-fault path to a self-heal issue."""
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from helpers import insert_prices
from stockpilot import ops, store
from stockpilot.calls import record
from stockpilot.jobs import doctor


def _px(db, symbol, closes):
    prev = [closes[0][1]] + [c for _, c in closes[:-1]]
    insert_prices(db, [(d, symbol, "NSE", "EQ", c, c, c, c, pc, 1000, 1e8, 10)
                       for (d, c), pc in zip(closes, prev)])


def _nifty(db, closes):
    for d, c in closes:
        db.execute("insert into index_levels (date, name, close) values (?, 'Nifty 50', ?)", [d, c])


def _call(db, symbol, made_on, p, horizon=91):
    db.execute("insert into calls (made_on, symbol, kind, action, probability, horizon_days) "
               "values (?, ?, 'candidate', 'buy', ?, ?)", [made_on, symbol, p, horizon])


# ---- scoring: worked examples ------------------------------------------------------------------

def test_scores_a_call_against_the_nifty_and_computes_hit_rate_and_brier(db):
    d0, d3 = date(2026, 1, 2), date(2026, 4, 3)           # 91 days
    _nifty(db, [(d0, 100.0), (d3, 110.0)])                # Nifty +10%
    _px(db, "WIN", [(d0, 100.0), (d3, 130.0)])            # +30%: beats it
    _px(db, "LOSE", [(d0, 100.0), (d3, 105.0)])           # +5%: lags it
    _call(db, "WIN", d0, 0.7)
    _call(db, "LOSE", d0, 0.8)
    assert record.score(db, date(2026, 4, 10)) == 2
    got = dict(db.execute("select symbol, score_3m from calls").fetchall())
    assert got == {"WIN": 1.0, "LOSE": 0.0}
    rec = record.summary(db)["3m"]
    assert rec["n"] == 2 and rec["hit_rate"] == 0.5
    assert rec["brier"] == pytest.approx(((0.7 - 1) ** 2 + (0.8 - 0) ** 2) / 2)   # 0.365


def test_a_horizon_that_has_not_ended_stays_unscored_and_scoring_is_idempotent(db):
    d0 = date(2026, 1, 2)
    _nifty(db, [(d0, 100.0), (date(2026, 2, 1), 101.0)])
    _px(db, "AAA", [(d0, 10.0), (date(2026, 2, 1), 12.0)])
    _call(db, "AAA", d0, 0.6)
    assert record.score(db, date(2026, 2, 2)) == 1        # only the 1-month window has ended
    row = db.execute("select score_1m, score_3m, score_6m from calls").fetchone()
    assert row == (1.0, None, None)
    assert record.score(db, date(2026, 2, 2)) == 0


def test_a_split_inside_the_window_is_not_a_loss(db):
    d0, d1, d2 = date(2026, 1, 2), date(2026, 1, 20), date(2026, 1, 30)
    _nifty(db, [(d0, 100.0), (d2, 101.0)])
    insert_prices(db, [(d0, "SPL", "NSE", "EQ", 1000, 1000, 1000, 1000, 1000, 1, 1e8, 1),
                       (d1, "SPL", "NSE", "EQ", 500, 500, 500, 500, 500, 1, 1e8, 1),   # 1:2 split
                       (d2, "SPL", "NSE", "EQ", 600, 600, 600, 600, 500, 1, 1e8, 1)])
    db.execute("insert into corporate_actions (symbol, ex_date, kind, numerator, denominator) "
               "values ('SPL', ?, 'split', 2, 1)", [d1])
    # The action table says 1:2 on d1. Real return 500 -> 600 = +20%.
    _call(db, "SPL", d0, 0.5)
    record.score(db, date(2026, 2, 5))
    assert db.execute("select score_1m from calls").fetchone()[0] == 1.0


def test_a_call_with_no_price_data_is_left_unscored(db):
    _call(db, "GONE", date(2026, 1, 2), 0.6)
    assert record.score(db, date(2026, 12, 1)) == 0


# ---- doctor --------------------------------------------------------------------------------------

NOW = datetime(2026, 11, 20, 21, 0)       # a Friday, after the daily run


def _run(db, job, status, at, notes="{}"):
    db.execute("insert into runs (job, status, started_at, finished_at, notes) values (?, ?, ?, ?, ?)",
               [job, status, at, at, notes])


def test_doctor_is_quiet_when_everything_is_fresh(db, tmp_path):
    _run(db, "daily_ingest", "ok", datetime(2026, 11, 20, 19, 0))
    _run(db, "daily_decide", "ok", datetime(2026, 11, 20, 19, 10))
    assert ops.diagnose(db, {}, NOW, tmp_path) == []


def test_doctor_flags_a_failed_daily_run_with_the_error(db, tmp_path):
    _run(db, "daily_ingest", "failed", datetime(2026, 11, 20, 19, 0),
         json.dumps({"failed": {"nse_prices": "bhavcopy not published yet"}}))
    found = ops.diagnose(db, {}, NOW, tmp_path)
    assert [f["key"] for f in found] == ["daily_ingest-failed"]
    assert "bhavcopy not published yet" in found[0]["detail"]


def test_doctor_flags_a_missing_run_on_a_trading_day_but_not_on_a_holiday(db, tmp_path):
    _run(db, "daily_ingest", "ok", datetime(2026, 11, 18, 19, 0))     # nothing since Wednesday
    _run(db, "daily_decide", "ok", datetime(2026, 11, 18, 19, 10))
    assert [f["key"] for f in ops.diagnose(db, {}, NOW, tmp_path)] == ["daily_ingest-stale"]
    db.execute("insert into holidays values (?, 'Holiday')", [date(2026, 11, 19)])
    db.execute("insert into holidays values (?, 'Holiday')", [date(2026, 11, 20)])
    assert ops.diagnose(db, {}, NOW, tmp_path) == []


def test_doctor_counts_down_token_expiry_and_checks_disk(db, tmp_path):
    _run(db, "daily_ingest", "ok", datetime(2026, 11, 20, 19, 0))
    _run(db, "daily_decide", "ok", datetime(2026, 11, 20, 19, 10))
    cfg = {"tokens": {"CLAUDE_CODE_OAUTH_TOKEN": {"issued": "2025-12-01", "lifetime_days": 365}}}
    found = ops.diagnose(db, cfg, NOW, tmp_path)
    assert [f["key"] for f in found] == ["token-CLAUDE_CODE_OAUTH_TOKEN"]      # 11 days left
    assert ops.diagnose(db, cfg, NOW, tmp_path, free_bytes=lambda p: 10**8)[-1]["key"] == "disk-low"


# ---- planted fault -> self-heal issue --------------------------------------------------------------

class FakeGh:
    def __init__(self, existing=()):
        self.calls, self.existing = [], list(existing)

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("issue", "list"):
            return json.dumps(self.existing)
        return "https://github.com/o/r/issues/7"


def test_a_planted_fault_opens_one_self_heal_issue_and_not_a_second(db, tmp_path):
    _run(db, "daily_ingest", "failed", datetime(2026, 11, 20, 19, 0), json.dumps({"failed": {"nse_prices": "boom"}}))
    db.execute("insert into problems (job, severity, message) values ('daily_ingest', 'error', 'nse_prices: boom')")
    gh = FakeGh()
    assert doctor.doctor(db, {}, NOW, tmp_path, gh) == 1
    create = [c for c in gh.calls if c[:2] == ("issue", "create")][0]
    assert "--label" in create and create[create.index("--label") + 1] == "self-heal"
    body = create[create.index("--body") + 1]
    assert "boom" in body and "job: daily_ingest" in body
    assert db.execute("select count(*) from problems where job = 'doctor' and issue_url is not null").fetchone()[0] == 1
    gh2 = FakeGh()
    assert doctor.doctor(db, {}, NOW, tmp_path, gh2) == 0                  # same fault, already filed
    assert not [c for c in gh2.calls if c[:2] == ("issue", "create")]


def test_a_cleared_fault_is_marked_resolved_so_it_can_be_filed_again(db, tmp_path):
    _run(db, "daily_ingest", "failed", datetime(2026, 11, 20, 19, 0))
    doctor.doctor(db, {}, NOW, tmp_path, FakeGh())
    _run(db, "daily_ingest", "ok", datetime(2026, 11, 20, 20, 0))
    doctor.doctor(db, {}, NOW, tmp_path, FakeGh())
    assert db.execute("select resolution from problems where job = 'doctor'").fetchone()[0] == "cleared"


def test_the_doctor_cli_files_the_issue_through_gh_on_the_path(tmp_path):
    root = tmp_path / "proj"
    (root / "config").mkdir(parents=True)
    (root / "config" / "stockpilot.yaml").write_text("store:\n  path: data/sp.duckdb\n")
    db = store.open(root / "data" / "sp.duckdb")
    _run(db, "daily_ingest", "failed", datetime.now() - timedelta(hours=1), json.dumps({"failed": {"x": "planted"}}))
    db.close()
    bin_dir, log = tmp_path / "bin", tmp_path / "gh.log"
    bin_dir.mkdir()
    shim = bin_dir / "gh"
    shim.write_text(f'#!/bin/sh\necho "$@" >> {log}\n[ "$1 $2" = "issue list" ] && echo "[]"\nexit 0\n')
    shim.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}"}
    out = subprocess.run([sys.executable, "-m", "stockpilot.cli", "--root", str(root), "doctor", "--no-push"],
                         env=env, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    assert "issue create" in log.read_text() and "self-heal" in log.read_text()


# ---- reruns requested by the self-heal Action -------------------------------------------------------

def test_a_rerun_requested_issue_reruns_the_named_job_and_reports(db, tmp_path):
    gh = FakeGh(existing=[{"number": 7, "body": "job: daily_ingest\nerror: x", "labels": [{"name": "rerun-requested"}]}])
    ran = []
    assert doctor.apply_reruns(gh, lambda job: ran.append(job) or 0) == 1
    assert ran == ["daily"]
    assert any(c[:2] == ("issue", "comment") for c in gh.calls)
    assert any(c[:2] == ("issue", "edit") and "--remove-label" in c for c in gh.calls)


# ---- status and publishing to branches ---------------------------------------------------------------

def _bare(tmp_path):
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    return str(bare)


def _show(remote, branch, path):
    return subprocess.run(["git", "--git-dir", remote, "show", f"{branch}:{path}"], capture_output=True,
                          text=True, check=True).stdout


def test_status_json_goes_to_the_status_branch_as_one_commit(db, tmp_path):
    _run(db, "daily_ingest", "ok", datetime(2026, 11, 20, 19, 0))
    _run(db, "daily_decide", "ok", datetime(2026, 11, 20, 19, 10))
    status = ops.build_status(db, {}, NOW, tmp_path)
    assert status["ok"] is True and status["last_ok"]["daily_ingest"].startswith("2026-11-20")
    remote = _bare(tmp_path)
    ops.push_status(remote, status)
    ops.push_status(remote, {**status, "generated_at": "later"})
    assert json.loads(_show(remote, "status", "status.json"))["generated_at"] == "later"
    count = subprocess.run(["git", "--git-dir", remote, "rev-list", "--count", "status"], capture_output=True,
                           text=True, check=True).stdout.strip()
    assert count == "1"


def test_archive_appends_each_day_and_never_rewrites_history(db, tmp_path):
    _call(db, "AAA", date(2026, 11, 20), 0.6)
    remote = _bare(tmp_path)
    assert ops.archive(db, remote, date(2026, 11, 20), tmp_path) is True
    first = subprocess.run(["git", "--git-dir", remote, "rev-parse", "archive"], capture_output=True, text=True).stdout
    _call(db, "BBB", date(2026, 11, 23), 0.6)
    ops.archive(db, remote, date(2026, 11, 23), tmp_path)
    log = subprocess.run(["git", "--git-dir", remote, "log", "--format=%H", "archive"], capture_output=True,
                         text=True).stdout.split()
    assert len(log) == 2 and log[1] == first.strip()
    assert json.loads(_show(remote, "archive", "2026-11-20/calls.json"))[0]["symbol"] == "AAA"
    assert ops.archive(db, remote, date(2026, 11, 23), tmp_path) is False        # already archived: no-op
    assert [str(d) for d, in db.execute("select day from archived_days order by day").fetchall()] == ["2026-11-20", "2026-11-23"]


# ---- units, workflows --------------------------------------------------------------------------------

ROOT = Path(__file__).parent.parent


def test_every_job_in_the_brief_has_a_unit_and_timer():
    names = {p.stem for p in (ROOT / "ops" / "systemd").glob("*.timer")}
    assert names == {"sp-tick", "sp-doctor", "sp-publish"}


@pytest.mark.skipif(not Path("/usr/bin/systemd-analyze").exists(), reason="no systemd-analyze")
def test_units_pass_systemd_analyze_verify(tmp_path):
    out = tmp_path / "units"
    fake = tmp_path / "proj" / ".venv" / "bin"
    fake.mkdir(parents=True)
    (fake / "sp").write_text("#!/bin/sh\n")
    (fake / "sp").chmod(0o755)
    subprocess.run(["bash", str(ROOT / "ops" / "install.sh"), "--render", str(out), "--root", str(tmp_path / "proj"),
                    "--user", "nobody"], check=True)
    units = sorted(str(p) for p in out.iterdir())
    assert len(units) >= 5
    res = subprocess.run(["systemd-analyze", "verify", *units], capture_output=True, text=True)
    assert res.returncode == 0 and "error" not in res.stderr.lower(), res.stderr


def test_workflows_are_valid_yaml_with_the_right_triggers():
    import yaml
    wf = ROOT / ".github" / "workflows"
    dog = yaml.safe_load((wf / "watchdog.yml").read_text())         # PyYAML reads `on` as True
    assert dog[True]["schedule"][0]["cron"] == "30 15 * * *"       # 21:00 IST
    ci = yaml.safe_load((wf / "ci.yml").read_text())
    assert "stage-1-skeleton" in ci[True]["push"]["branches"] and {"python", "web", "dashboard"} <= set(ci["jobs"])


def test_watchdog_verdicts():
    sys.path.insert(0, str(ROOT / "ops"))
    import watchdog
    fresh = {"generated_at": "2026-11-20T14:00:00+00:00", "holidays": []}
    now = datetime.fromisoformat("2026-11-20T15:30:00+00:00")
    assert watchdog.verdict(fresh, now) == "ok"
    stale = {"generated_at": "2026-11-20T08:00:00+00:00", "holidays": []}
    assert watchdog.verdict(stale, now) == "reset"
    assert watchdog.verdict(stale, datetime.fromisoformat("2026-11-22T15:30:00+00:00")) == "ok"       # Sunday
    assert watchdog.verdict({**stale, "holidays": ["2026-11-20"]}, now) == "ok"
    assert watchdog.verdict(None, now) == "reset"


# ---- the doctor watches decide, and a waiting ingest is not a fault before 23:00 -------------------------------

def _keys(db, tmp_path, now=NOW):
    return [f["key"] for f in ops.diagnose(db, {}, now, tmp_path)]


def test_a_failed_decide_is_a_fault(db, tmp_path):
    _run(db, "daily_ingest", "ok", datetime(2026, 11, 20, 19, 0))
    _run(db, "daily_decide", "failed", datetime(2026, 11, 20, 19, 10))
    assert _keys(db, tmp_path) == ["daily_decide-failed"]


def test_no_decide_after_an_ok_ingest_is_stale(db, tmp_path):
    _run(db, "daily_ingest", "ok", datetime(2026, 11, 20, 19, 0))
    assert _keys(db, tmp_path) == []                                          # the crunch is only due by 22:00 (R14)
    assert _keys(db, tmp_path, datetime(2026, 11, 20, 22, 40)) == ["daily_decide-stale"]


def test_a_decide_that_is_still_running_is_not_stale_yet(db, tmp_path):
    _run(db, "daily_ingest", "ok", datetime(2026, 11, 20, 19, 0))
    _run(db, "daily_decide", "running", datetime(2026, 11, 20, 20, 30))
    assert _keys(db, tmp_path) == []
    assert _keys(db, tmp_path, datetime(2026, 11, 20, 23, 45)) == ["daily_decide-stale"]   # running for 3 h: stuck


def test_an_ok_decide_after_the_ingest_is_quiet(db, tmp_path):
    _run(db, "daily_ingest", "ok", datetime(2026, 11, 20, 19, 0))
    _run(db, "daily_decide", "ok", datetime(2026, 11, 20, 19, 10))
    assert _keys(db, tmp_path) == []


def test_a_decide_from_an_earlier_day_does_not_count(db, tmp_path):
    _run(db, "daily_decide", "ok", datetime(2026, 11, 19, 19, 10))
    _run(db, "daily_ingest", "ok", datetime(2026, 11, 20, 19, 0))
    assert _keys(db, tmp_path) == []                                          # the crunch is only due by 22:00 (R14)
    assert _keys(db, tmp_path, datetime(2026, 11, 20, 22, 40)) == ["daily_decide-stale"]


def test_a_waiting_ingest_is_not_a_fault_before_23(db, tmp_path):
    _run(db, "daily_ingest", "waiting", datetime(2026, 11, 20, 19, 0), json.dumps({"note": "NSE has not published 2026-11-20 yet"}))
    assert _keys(db, tmp_path, datetime(2026, 11, 20, 22, 59)) == []
    late = ops.diagnose(db, {}, datetime(2026, 11, 20, 23, 5), tmp_path)
    assert [f["key"] for f in late] == ["daily_ingest-stale"]
    assert "NSE" in late[0]["detail"]


def test_a_waiting_ingest_raises_no_decide_fault(db, tmp_path):
    _run(db, "daily_ingest", "waiting", datetime(2026, 11, 20, 19, 0))
    assert "daily_decide-stale" not in _keys(db, tmp_path)


def test_install_removes_units_that_are_no_longer_in_the_folder(tmp_path):
    out = tmp_path / "units"
    out.mkdir()
    for old in ("sp-daily.timer", "sp-daily.service", "sp-queue.timer", "sp-nav.service", "sp-weekly.timer", "other.service"):
        (out / old).write_text("old")
    done = subprocess.run(["bash", str(ROOT / "ops" / "install.sh"), "--render", str(out), "--root", str(tmp_path / "proj"),
                           "--user", "nobody"], check=True, capture_output=True, text=True)
    left = sorted(p.name for p in out.iterdir())
    assert left == ["other.service", "sp-doctor.service", "sp-doctor.timer", "sp-onfailure.service",
                    "sp-publish.service", "sp-publish.timer", "sp-tick.service", "sp-tick.timer"]
    assert "Removed sp-daily.timer" in done.stdout


def test_the_tick_timer_runs_at_3_past_every_10_minutes_and_the_unit_accepts_75():
    timer = (ROOT / "ops" / "systemd" / "sp-tick.timer").read_text()
    unit = (ROOT / "ops" / "systemd" / "sp-tick.service").read_text()
    assert "OnCalendar=*-*-* *:03/10:00 Asia/Kolkata" in timer
    assert "TimeoutStartSec=3h" in unit and "SuccessExitStatus=75" in unit and "OnFailure=sp-onfailure.service" in unit
    assert "ExecStopPost" not in unit                  # ship is the end of the daily job, not a stop hook
