"""V1: the one-minute check. Model chains, GitHub starts, stale alarm, and the idle cost. Every model is a fake."""
from datetime import datetime, timedelta, timezone

import pytest

from stockpilot import jobrun
from stockpilot.jobs import minute

IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 11, 25, 9, 15, tzinfo=IST)


class Backend:
    def __init__(self, name, answer="ok", refuse=False):
        self.name, self.answer, self.refuse, self.calls = name, answer, refuse, 0

    def ask(self, prompt):
        self.calls += 1
        if self.refuse:
            raise minute.Refused(self.name)
        return self.answer


def chain(*backends):
    return minute.Chain(list(backends))


def test_first_backend_that_answers_wins_and_later_ones_are_untouched():
    a, b = Backend("sonnet", "A"), Backend("gemini", "B")
    assert chain(a, b).ask("q") == "A" and b.calls == 0


def test_a_refusing_backend_falls_through_to_the_next():
    a, b = Backend("sonnet", refuse=True), Backend("gemini", "B")
    c = chain(a, b)
    assert c.ask("q") == "B" and c.used == "gemini"


def test_tagging_chain_goes_gemini_a_then_b_then_haiku():
    names = [b.name for b in minute.chain_for("news_tag", lambda n: Backend(n)).backends]
    assert names == ["gemini-a", "gemini-b", "haiku"]
    assert [b.name for b in minute.chain_for("feedback_read", lambda n: Backend(n)).backends] == names


def test_forecast_chain_goes_sonnet_then_gemini():
    for kind in ("analyse", "refresh_call", "weekly_review"):
        assert [b.name for b in minute.chain_for(kind, lambda n: Backend(n)).backends] == ["sonnet", "gemini-a"]


def test_quota_message_when_every_model_refuses():
    c = chain(Backend("sonnet", refuse=True), Backend("gemini-a", refuse=True))
    with pytest.raises(jobrun.JobFailed) as err:
        c.ask("q")
    assert err.value.text == "Usage is used up. Try again in about an hour."
    assert err.value.text_bn


# ---- the tick -------------------------------------------------------------------------------------------------
def job(i, kind, payload=None, status="queued"):
    payload = {"symbol": "AAA", "exchange": "NSE"} if payload is None and kind == "analyse" else (payload or {})
    return {"id": f"job_{i}", "kind": kind, "payload": payload, "asked_by": "owner", "status": status, "result": None,
            "error": None, "error_bn": None, "created_at": f"2026-11-25T09:1{i}:00+05:30", "started_at": None, "finished_at": None}


class Source:
    def __init__(self, queued=(), last_nightly="2026-11-25T02:00:00+05:30"):
        self.queued, self.last_nightly, self.reads = list(queued), last_nightly, 0

    def pending(self):
        self.reads += 1
        return {"queued": self.queued, "last_nightly": self.last_nightly}


class Env:
    def __init__(self, source, backends=None, github_ok=True):
        self.source, self.sink = source, jobrun.MemorySink()
        self.github, self.alarms, self.state = [], [], {}
        self.backends = backends or {}
        self.github_ok = github_ok
        self.made = []

    def make(self, name):
        self.made.append(name)
        return self.backends.setdefault(name, Backend(name, f"answer from {name}"))

    def fire(self, now=T0, handlers=None):
        def start_github(j):
            if not self.github_ok:
                raise RuntimeError("no token")
            self.github.append(j["kind"])
        return minute.tick(self.source, self.sink, make_backend=self.make, handlers=handlers or {"analyse": minute.ask_handler("Analyse: {symbol}")},
                           start_github=start_github, alarm=self.alarms.append, state=self.state, now=lambda: now)


def test_idle_tick_does_one_read_and_nothing_else():
    env = Env(Source())
    out = env.fire()
    assert env.source.reads == 1 and out == {"ran": 0, "started": 0, "alarm": False}
    assert env.made == [] and env.github == [] and env.alarms == []


def test_analyse_job_runs_through_the_chain_and_finishes_with_lines():
    env = Env(Source([job(1, "analyse")]))
    assert env.fire()["ran"] == 1
    row = env.sink.jobs["job_1"]
    assert row["status"] == "done" and "answer from sonnet" in row["result"]
    assert [l["state"] for l in env.sink.lines["job_1"]][-1] == "ok"


def test_analyse_falls_to_gemini_when_sonnet_refuses():
    env = Env(Source([job(1, "analyse")]), {"sonnet": Backend("sonnet", refuse=True)})
    env.fire()
    assert "answer from gemini-a" in env.sink.jobs["job_1"]["result"]


def test_quota_message_lands_on_the_job_when_both_refuse():
    env = Env(Source([job(1, "analyse")]), {"sonnet": Backend("sonnet", refuse=True), "gemini-a": Backend("gemini-a", refuse=True)})
    env.fire()
    row = env.sink.jobs["job_1"]
    assert row["status"] == "failed" and row["error"] == minute.QUOTA and row["error_bn"] == minute.QUOTA_BN


def test_github_jobs_are_started_and_marked_running():
    env = Env(Source([job(1, "nightly"), job(2, "load_stock", {"symbol": "AAA", "exchange": "NSE"})]))
    out = env.fire()
    assert env.github == ["nightly", "load_stock"] and out["started"] == 2
    assert env.sink.jobs["job_1"]["status"] == "running"
    assert env.sink.lines["job_1"][0]["text"].startswith("Started on GitHub")


def test_a_github_start_that_fails_fails_the_job_in_plain_words():
    env = Env(Source([job(1, "nightly")]), github_ok=False)
    env.fire()
    row = env.sink.jobs["job_1"]
    assert row["status"] == "failed" and "token" not in row["error"]


def test_private_jobs_and_kinds_without_a_handler_stay_queued():
    env = Env(Source([job(1, "backup"), job(2, "news_tag", {"batch": "x"})]))
    out = env.fire()
    assert out == {"ran": 0, "started": 0, "alarm": False}
    assert all(j["status"] == "queued" for j in env.sink.jobs.values())


def test_stale_pipeline_alarm_once_per_six_hours():
    env = Env(Source(last_nightly="2026-11-23T02:00:00+05:30"))
    assert env.fire()["alarm"] is True and len(env.alarms) == 1
    assert env.fire(T0 + timedelta(hours=1))["alarm"] is False and len(env.alarms) == 1
    assert env.fire(T0 + timedelta(hours=7))["alarm"] is True and len(env.alarms) == 2


def test_fresh_pipeline_raises_no_alarm_and_never_before_a_first_nightly():
    assert Env(Source()).fire()["alarm"] is False
    assert Env(Source(last_nightly=None)).fire()["alarm"] is False


# ---- D1 over HTTP ---------------------------------------------------------------------------------------------
import json as _json
import sqlite3
from pathlib import Path

MIGRATION = Path(__file__).resolve().parents[2] / "web" / "migrations" / "0001_live_contract.sql"


def local_d1():
    """A fake of Cloudflare's query endpoint: `query(sql, params) -> rows` over SQLite with the real migration."""
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript(MIGRATION.read_text())
    calls = []

    def query(sql, params=()):
        calls.append(sql)
        cur = db.execute(sql, list(params))
        db.commit()
        return [dict(r) for r in cur.fetchall()]
    return db, query, calls


def seed(db, row):
    db.execute("insert into jobs (id,kind,payload,asked_by,status,created_at) values (?,?,?,?,?,?)",
               (row["id"], row["kind"], _json.dumps(row["payload"]), row["asked_by"], row["status"], row["created_at"]))
    db.commit()


def test_d1_source_idle_is_one_query_with_the_last_nightly():
    db, query, calls = local_d1()
    src = minute.D1Source(query)
    assert src.pending() == {"queued": [], "running_github": [], "last_nightly": None, "last_weekly": None, "untagged": 0,
                             "open_kinds": set()} and len(calls) == 1
    db.execute("insert into jobs (id,kind,payload,asked_by,status,created_at,finished_at) values ('n1','nightly','{}','system','done','2026-11-25T02:00:00+05:30','2026-11-25T02:30:00+05:30')")
    assert src.pending()["last_nightly"] == "2026-11-25T02:30:00+05:30"


def test_d1_source_returns_queued_rows_oldest_first_with_json_payloads():
    db, query, _ = local_d1()
    seed(db, job(2, "analyse"))
    seed(db, job(1, "analyse"))
    got = minute.D1Source(query).pending()["queued"]
    assert [r["id"] for r in got] == ["job_1", "job_2"] and got[0]["payload"] == {"symbol": "AAA", "exchange": "NSE"}


def test_a_job_run_through_the_d1_sink_lands_in_the_tables():
    db, query, _ = local_d1()
    seed(db, job(1, "analyse"))
    src, sink = minute.D1Source(query), jobrun.SqliteSink(minute.D1Db(query))
    out = minute.tick(src, sink, make_backend=lambda n: Backend(n, "fine"), handlers={"analyse": minute.ask_handler("x {symbol}")},
                      start_github=lambda j: None, alarm=lambda t: None, state={}, now=lambda: T0)
    assert out["ran"] == 1
    assert db.execute("select status from jobs where id='job_1'").fetchone()[0] == "done"
    assert db.execute("select count(*) from job_lines where job_id='job_1'").fetchone()[0] >= 2


def test_cloudflare_http_query_sends_the_token_and_unwraps_rows():
    seen = {}

    def post(url, headers, body):
        seen.update(url=url, headers=headers, body=body)
        return {"success": True, "result": [{"results": [{"a": 1}]}]}
    q = minute.cloudflare_query("acct", "dbid", "tok", post)
    assert q("select ?", [1]) == [{"a": 1}]
    assert "acct" in seen["url"] and "dbid" in seen["url"] and seen["headers"]["Authorization"] == "Bearer tok"
    assert seen["body"] == {"sql": "select ?", "params": [1]}
    with pytest.raises(RuntimeError):
        minute.cloudflare_query("a", "d", "t", lambda *a: {"success": False, "errors": [{"message": "bad"}]})("x")


def test_github_kind_with_no_workflow_stays_queued_and_unmarked():
    env = Env(Source([job(1, "nightly")]))
    starter = minute.gh_starter({})
    out = minute.tick(env.source, env.sink, make_backend=env.make, handlers={}, start_github=starter, alarm=env.alarms.append,
                      state={}, now=lambda: T0)
    assert out["started"] == 0 and "job_1" not in env.sink.jobs


def test_gh_starter_passes_job_id_and_payload_as_inputs():
    seen = []

    class Done: returncode, stderr = 0, ""
    start = minute.gh_starter({"load_stock": "stock-facts.yml"}, run=lambda a, **k: seen.append(a) or Done())
    start(job(1, "load_stock", {"symbol": "AAA", "exchange": "NSE"}))
    assert seen[0][:4] == ["gh", "workflow", "run", "stock-facts.yml"] and "job_id=job_1" in seen[0] and "symbol=AAA" in seen[0]


def test_unconfigured_firing_exits_75_and_idle_import_adds_under_20_mb(tmp_path):
    import subprocess, sys
    code = ("import resource,sys\nbase=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss//1024\n"
            "from stockpilot import config;from stockpilot.jobs import minute\n"
            "rc=minute.run(config.load(sys.argv[1]))\n"
            "print(rc, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss//1024-base)")
    done = subprocess.run([sys.executable, "-c", code, str(tmp_path)], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path), "PYTHONPATH": ":".join(sys.path)})
    rc, mb = done.stdout.split()
    assert rc == "75" and int(mb) < 20, done.stderr          # the VM's real idle number is in the PR's VM steps
