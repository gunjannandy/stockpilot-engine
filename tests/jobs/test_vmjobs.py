"""The VM job runner: job files on branch vm-jobs in, result files out. Real git against a temp remote; every other command is faked."""
import json
import subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from stockpilot.jobs import vmjobs

IST = timezone(timedelta(hours=5, minutes=30))
NOON = datetime(2026, 11, 25, 12, 0, tzinfo=IST)
OK_EMAIL = "owner@example.com"


def git(cwd, *argv, env=None):
    return subprocess.run(["git", *argv], cwd=cwd, check=True, capture_output=True, text=True,
                          env={"GIT_AUTHOR_NAME": "t", "GIT_COMMITTER_NAME": "t", "GIT_AUTHOR_EMAIL": OK_EMAIL,
                               "GIT_COMMITTER_EMAIL": OK_EMAIL, "PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd), **(env or {})}).stdout


class World:
    """A bare remote, a requester clone that pushes job files, the runner's root checkout and its queue clone."""

    def __init__(self, tmp):
        self.remote = tmp / "remote.git"
        subprocess.run(["git", "init", "--bare", "-b", "main", str(self.remote)], check=True, capture_output=True)
        self.root = tmp / "root"
        self.root.mkdir()
        git(self.root, "init", "-b", "stage-1-skeleton")
        (self.root / "ops" / "vm-jobs").mkdir(parents=True)
        (self.root / "ops/vm-jobs/allowed_requesters.txt").write_text(f"# who may ask\n{OK_EMAIL}\n")
        (self.root / ".env").write_text("CLAUDE_CODE_OAUTH_TOKEN=sk-ant-oat01-SECRETSECRET\nSNAPSHOT_AGE_RECIPIENT=age1recipientrecipient\n")
        git(self.root, "add", "-A", "-f")
        git(self.root, "commit", "-m", "root")
        git(self.root, "remote", "add", "origin", str(self.remote))
        git(self.root, "push", "origin", "stage-1-skeleton")
        self.req = tmp / "req"
        git(tmp, "clone", str(self.remote), str(self.req))
        git(self.req, "checkout", "-b", "vm-jobs")
        (self.req / "README").write_text("jobs\n")
        git(self.req, "add", "-A")
        git(self.req, "commit", "-m", "init")
        git(self.req, "push", "origin", "vm-jobs")
        self.queue = tmp / "queue"
        self.calls = []
        self.outputs = {}
        self.codes = {}

    def request(self, id, job, args=None, email=OK_EMAIL, raw=None):
        (self.req / "jobs").mkdir(exist_ok=True)
        (self.req / "jobs" / f"{id}.json").write_text(raw if raw is not None else json.dumps(
            {"id": id, "job": job, "args": args or {}, "requested_by": "owner"}))
        git(self.req, "add", "-A")
        git(self.req, "commit", "-m", f"job {id}", env={"GIT_AUTHOR_EMAIL": email})
        git(self.req, "push", "origin", "vm-jobs")

    def fake_run(self, argv, cwd=None, env=None):
        if argv[0] == "git":
            done = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                                  env={"PATH": "/usr/bin:/bin", "HOME": str(self.root), "GIT_AUTHOR_NAME": "r", "GIT_COMMITTER_NAME": "r",
                                       "GIT_AUTHOR_EMAIL": "runner@example.com", "GIT_COMMITTER_EMAIL": "runner@example.com"})
            return done.returncode, done.stdout + done.stderr
        self.calls.append((argv, cwd, dict(env or {})))
        text = " ".join(argv[3:]) if argv[0].endswith("sp") else " ".join(argv)
        for needle, out in self.outputs.items():
            if needle in text:
                return self.codes.get(needle, 0), out
        return 0, ""

    def runner(self, now=NOON, dry_run=False, http_ok=lambda url: True):
        return vmjobs.Runner(root=self.root, queue=self.queue, run=self.fake_run, now=lambda: now, dry_run=dry_run,
                             http_ok=http_ok, sp=["/venv/bin/sp", "--root", str(self.root)], wrangler="/bin/wrangler")

    def result(self, id):
        git(self.req, "pull", "-q", "origin", "vm-jobs")
        path = self.req / "results" / f"{id}.json"
        return json.loads(path.read_text()) if path.exists() else None

    def sp_calls(self):
        return [c[0][3:] for c in self.calls if c[0][0] == "/venv/bin/sp"]


@pytest.fixture
def world(tmp_path):
    return World(tmp_path)


def test_a_job_runs_and_its_result_is_pushed(world):
    world.request("a1", "build-site")
    done = world.runner().poll()
    assert [r["id"] for r in done] == ["a1"]
    res = world.result("a1")
    assert res["status"] == "ok" and res["exit"] == 0
    assert set(res) >= {"id", "status", "started", "finished", "exit", "log_tail", "outputs"}
    assert world.sp_calls() == [["build-site"]]


def test_a_job_with_a_result_is_not_run_again(world):
    world.request("a1", "build-site")
    world.runner().poll()
    world.calls.clear()
    assert world.runner().poll() == []
    assert world.calls == []


def test_nothing_runs_outside_nine_to_five_ist(world):
    world.request("a1", "build-site")
    assert world.runner(now=datetime(2026, 11, 25, 8, 59, tzinfo=IST)).poll() == []
    assert world.runner(now=datetime(2026, 11, 25, 17, 1, tzinfo=IST)).poll() == []
    # a UTC clock is converted, not trusted: 06:00 UTC is 11:30 IST
    assert world.runner(now=datetime(2026, 11, 25, 6, 0, tzinfo=timezone.utc)).poll() != []
    assert world.calls


def test_a_missing_jobs_branch_is_a_quiet_nothing(world):
    git(world.remote, "branch", "-D", "vm-jobs")
    assert world.runner().poll() == []


def test_jobs_run_in_the_order_they_were_requested_one_at_a_time(world):
    for i in ("b3", "a9", "c1"):
        world.request(i, "build-site")
    assert [r["id"] for r in world.runner().poll()] == ["b3", "a9", "c1"]


@pytest.mark.parametrize("job,args", [
    ("rm-rf", {}), ("build-site", {"x": 1}), ("decide-refresh", {"date": "tomorrow"}), ("decide-refresh", {"date": "2026-11-25; rm -rf /"}),
    ("deploy", {"ref": "main"}), ("verify", "nope"), ("snapshot-publish", {"tag": "x"}),
])
def test_unknown_jobs_and_bad_args_are_rejected_without_running_anything(world, job, args):
    world.request("r1", job, args)
    world.runner().poll()
    res = world.result("r1")
    assert res["status"] == "rejected" and res["exit"] is None and res["log_tail"]
    assert world.calls == []


def test_a_job_file_from_an_unlisted_author_is_rejected(world):
    world.request("x1", "build-site", email="stranger@example.com")
    world.runner().poll()
    assert world.result("x1")["status"] == "rejected"
    assert "author" in " ".join(world.result("x1")["log_tail"])
    assert world.calls == []


def test_the_allow_list_comes_from_the_trusted_checkout_not_the_jobs_branch(world):
    (world.req / "ops/vm-jobs").mkdir(parents=True)
    (world.req / "ops/vm-jobs/allowed_requesters.txt").write_text("stranger@example.com\n")
    git(world.req, "add", "-A")
    git(world.req, "commit", "-m", "sneak", env={"GIT_AUTHOR_EMAIL": "stranger@example.com"})
    git(world.req, "push", "origin", "vm-jobs")
    world.request("x2", "build-site", email="stranger@example.com")
    world.runner().poll()
    assert world.result("x2")["status"] == "rejected"


def test_a_job_file_whose_id_does_not_match_or_is_not_json_is_rejected(world):
    world.request("m1", "build-site", raw=json.dumps({"id": "other", "job": "build-site", "args": {}, "requested_by": "o"}))
    world.request("m2", "build-site", raw="{not json")
    world.runner().poll()
    assert world.result("m1")["status"] == "rejected" and world.result("m2")["status"] == "rejected"
    assert world.calls == []


def test_a_failing_command_marks_the_job_failed_with_its_exit(world):
    world.outputs["build-site"] = "boom"
    world.codes["build-site"] = 3
    world.request("f1", "build-site")
    world.runner().poll()
    res = world.result("f1")
    assert res["status"] == "failed" and res["exit"] == 3 and "boom" in "\n".join(res["log_tail"])


def test_log_tail_is_the_last_200_lines_with_secrets_scrubbed(world):
    world.outputs["build-site"] = "\n".join(f"line {i}" for i in range(500)) + \
        "\ntoken sk-ant-oat01-SECRETSECRET and AGE-SECRET-KEY-1QQQQQQQQQQQQQQQQQQQQQQQQ and ghp_abcdefghijklmnopqrstuvwxyz0123456789"
    world.request("s1", "build-site")
    world.runner().poll()
    tail = world.result("s1")["log_tail"]
    assert len(tail) == 200 and tail[0] == "line 301"
    text = "\n".join(tail)
    assert "SECRETSECRET" not in text and "AGE-SECRET-KEY" not in text and "ghp_" not in text and "[hidden]" in text


def test_verify_is_build_verify_build_verify(world):
    world.request("v1", "verify")
    world.runner().poll()
    assert world.sp_calls() == [["build-site"], ["verify"], ["build-site"], ["verify"]]
    assert world.result("v1")["status"] == "ok"


@pytest.mark.parametrize("codes,status", [([1, 0], "ok"), ([0, 1], "failed")])
def test_the_second_verify_is_the_gate_not_the_first(world, codes, status):
    verifies = iter(codes)
    base = world.fake_run

    def run(argv, cwd=None, env=None):
        if argv[-1] == "verify":
            world.calls.append((argv, cwd, env))
            return next(verifies), "x"
        return base(argv, cwd, env)
    world.fake_run = run
    world.request("v2", "verify")
    world.runner().poll()
    assert world.result("v2")["status"] == status


def test_deploy_holds_back_when_the_gate_fails(world):
    world.codes["verify"] = 1
    world.outputs["verify"] = "hard failure"
    world.request("d1", "deploy")
    world.runner().poll()
    res = world.result("d1")
    assert res["status"] == "failed" and res["outputs"].get("deployed") is False
    assert not [c for c in world.calls if "wrangler" in c[0][0]]
    assert "main" not in git(world.remote, "branch", "--list", "main")


def test_deploy_runs_wrangler_after_the_gate_records_the_id_and_fast_forwards_main(world):
    world.outputs["pages deployment list"] = json.dumps([{"Id": "dep-123", "Environment": "production"}])
    world.request("d2", "deploy")
    world.runner().poll()
    res = world.result("d2")
    assert res["status"] == "ok" and res["outputs"]["deployment_id"] == "dep-123" and res["outputs"]["main"] == "fast-forwarded"
    order = [" ".join(c[0][3:]) if c[0][0].endswith("sp") else c[0][0] for c in world.calls]
    assert order[:4] == ["build-site", "verify", "build-site", "verify"] and "/bin/wrangler" in order[4:]
    deploy = [c for c in world.calls if c[0][:3] == ["/bin/wrangler", "pages", "deploy"]][0]
    assert deploy[0][3:] == ["../site", "--project-name", "stockpilotgn", "--branch", "main"] and deploy[1] == world.root / "web"
    assert git(world.remote, "rev-parse", "main").strip() == git(world.root, "rev-parse", "HEAD").strip()


def test_a_failed_wrangler_deploy_leaves_main_alone(world):
    world.codes["pages deploy"] = 1
    world.outputs["pages deploy"] = "no"
    world.request("d3", "deploy")
    world.runner().poll()
    assert world.result("d3")["status"] == "failed"
    assert "main" not in git(world.remote, "branch", "--list", "main")


def test_a_live_site_that_does_not_load_leaves_main_alone_and_names_the_previous_deployment(world):
    world.outputs["pages deployment list"] = json.dumps([{"Id": "new"}, {"Id": "old"}])
    world.request("d4", "deploy")
    world.runner(http_ok=lambda url: False).poll()
    res = world.result("d4")
    assert res["status"] == "failed" and res["outputs"]["rollback_to"] == "old"
    assert "main" not in git(world.remote, "branch", "--list", "main")


def test_snapshot_publish_uses_the_market_backup_with_a_key_from_env_and_never_prints_it(world):
    world.outputs["backup market"] = "Market data uploaded: age1recipientrecipient"
    world.request("p1", "snapshot-publish")
    world.runner().poll()
    assert world.sp_calls() == [["backup", "market", "--tag", "market-snapshot", "--recipient-env", "SNAPSHOT_AGE_RECIPIENT"]]
    res = world.result("p1")
    assert res["status"] == "ok" and "age1recipientrecipient" not in json.dumps(res)


def test_decide_refresh_runs_the_supported_daily_path_with_the_setup_token_only(world):
    world.request("n1", "decide-refresh", {"date": "2026-11-24"})
    world.runner().poll()
    assert world.sp_calls() == [["daily", "--date", "2026-11-24"]]
    env = [c for c in world.calls][0][2]
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "sk-ant-oat01-SECRETSECRET" and "ANTHROPIC_API_KEY" not in env


def test_every_command_is_an_argument_list_never_a_shell_string(world, monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "leak")
    world.request("n2", "decide-refresh", {"date": "2026-11-24"})
    world.request("n3", "deploy")
    world.runner().poll()
    assert world.calls and all(isinstance(c[0], list) and all(isinstance(a, str) for a in c[0]) for c in world.calls)
    assert all("ANTHROPIC_API_KEY" not in c[2] for c in world.calls)


def test_dry_run_plans_but_runs_and_pushes_nothing(world):
    world.request("y1", "deploy")
    plan = world.runner(dry_run=True).poll()
    assert plan[0]["id"] == "y1" and plan[0]["status"] == "dry-run" and plan[0]["would_run"]
    assert world.calls == [] and world.result("y1") is None
    assert "main" not in git(world.remote, "branch", "--list", "main")


def test_a_second_runner_does_nothing_while_one_holds_the_lock(world):
    world.request("l1", "build-site")
    with vmjobs.locked(world.queue.parent / "vm-jobs.lock"):
        assert world.runner().poll() == []
    assert world.calls == []
    assert [r["id"] for r in world.runner().poll()] == ["l1"]


def test_the_timer_unit_is_a_oneshot_with_a_memory_cap_and_fires_only_in_working_hours(tmp_path):
    root = Path(__file__).resolve().parents[2]
    out = tmp_path / "units"
    done = subprocess.run(["bash", str(root / "ops/vm-jobs/install.sh"), "--render", str(out), "--root", str(tmp_path / "proj"), "--user", "nobody"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    service = (out / "sp-vm-jobs.service").read_text()
    timer = (out / "sp-vm-jobs.timer").read_text()
    assert "Type=oneshot" in service and "MemoryMax=700M" in service and str(tmp_path / "proj") in service and "@" not in service
    assert "Asia/Kolkata" in timer and "00/2" in timer and "09..16" in timer and "17:00" in timer
    assert "Persistent" not in timer.replace("Persistent=false", "")


def test_backup_market_takes_a_tag_and_a_key_from_env_and_never_echoes_the_key(tmp_path, monkeypatch, capsys):
    from pyrage import x25519
    from stockpilot import backup, cli, store
    (tmp_path / "data").mkdir()
    (tmp_path / "config").mkdir()
    store.open(tmp_path / "data/stockpilot.duckdb").close()
    key = x25519.Identity.generate().to_public()
    (tmp_path / ".env").write_text(f"{vmjobs.SNAPSHOT_KEY}={key}\n")
    uploads = []
    monkeypatch.setattr(backup, "gh_upload", lambda tag, files: uploads.append((tag, [f.name for f in files])))
    assert cli.main(["--root", str(tmp_path), "backup", "market", "--tag", "market-snapshot", "--recipient-env", vmjobs.SNAPSHOT_KEY]) == 0
    assert uploads[0][0] == "market-snapshot" and "manifest.json" in uploads[0][1]
    assert str(key) not in capsys.readouterr().out
    (tmp_path / ".env").write_text(f"{vmjobs.SNAPSHOT_KEY}=nonsense\n")
    with pytest.raises(SystemExit) as err:
        cli.main(["--root", str(tmp_path), "backup", "market", "--recipient-env", vmjobs.SNAPSHOT_KEY])
    assert "nonsense" not in str(err.value)
