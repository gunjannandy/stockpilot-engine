"""T14: one entry point for every job kind. Rows are in the live contract's format; the model is always a fake."""
import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stockpilot import jobrun

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((ROOT / "schemas" / "live-contract.json").read_text())
IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 11, 25, 9, 15, tzinfo=IST)


class Clock:
    def __init__(self):
        self.now = T0

    def __call__(self):
        self.now += timedelta(seconds=10)
        return self.now


class FakeModel:
    def __init__(self, answer="ok"):
        self.answer, self.calls = answer, []

    def ask(self, prompt):
        self.calls.append(prompt)
        return self.answer


def runner(sink=None, model=None):
    sink = sink or jobrun.MemorySink()
    return jobrun.JobRunner(sink, model=model, clock=Clock()), sink


def fixture_job(ctx):
    ctx.progress("Logging in", "ঢুকছি")
    ctx.progress("Logged in", state="ok")
    return "Done, 3 changes"


def test_fixture_job_writes_queued_running_progress_and_done():
    r, sink = runner()
    r.register("sync", fixture_job)
    job_id = r.enqueue("sync", {}, asked_by="father")
    assert sink.jobs[job_id]["status"] == "queued" and sink.lines[job_id] == []
    r.run(job_id)
    job = sink.jobs[job_id]
    assert job["status"] == "done" and job["result"] == "Done, 3 changes" and job["error"] is None
    assert job["started_at"] and job["finished_at"] and job["started_at"] <= job["finished_at"]
    lines = sink.lines[job_id]
    assert [l["seq"] for l in lines] == [1, 2, 3]
    assert [l["state"] for l in lines] == ["info", "ok", "ok"]
    assert lines[0]["text_bn"] == "ঢুকছি"
    assert lines[-1]["text"] == job["result"]            # contract: last line says the result in the same words
    assert sink.history[job_id] == ["queued", "running", "done"]


def test_rows_match_the_contract_shapes():
    r, sink = runner()
    r.register("sync", fixture_job)
    job_id = r.run(r.enqueue("sync", {}, asked_by="owner"))
    assert jobrun.check_shape(sink.jobs[job_id], {k: v for k, v in CONTRACT["tables"]["jobs"]["columns"].items()}) == []
    for line in sink.lines[job_id]:
        assert jobrun.check_shape(line, CONTRACT["progress_line"]["shape"]) == []


def test_failing_job_writes_failed_with_a_plain_reason():
    def boom(ctx):
        ctx.progress("Fetching holdings")
        raise KeyError("holdings['x'] at /home/ubuntu/stockpilot/src/stockpilot/foo.py line 9")
    r, sink = runner()
    r.register("sync", boom)
    job_id = r.run(r.enqueue("sync", {}, asked_by="father"))
    job = sink.jobs[job_id]
    assert job["status"] == "failed" and job["result"] is None and job["finished_at"]
    assert job["error"] and "KeyError" not in job["error"] and "/home" not in job["error"] and "Traceback" not in job["error"]
    last = sink.lines[job_id][-1]
    assert last["state"] == "fail" and last["text"] == job["error"]
    assert [l["seq"] for l in sink.lines[job_id]] == [1, 2]


def test_a_job_can_say_its_own_failure_in_words():
    def no_model(ctx):
        raise jobrun.JobFailed("No model is available. Usage is used up; try again in about an hour.",
                               "মডেল পাওয়া যাচ্ছে না।")
    r, sink = runner()
    r.register("news_tag", no_model)
    job_id = r.run(r.enqueue("news_tag", {"batch": "b1"}, asked_by="system"))
    job = sink.jobs[job_id]
    assert job["error"].startswith("No model is available") and job["error_bn"] == "মডেল পাওয়া যাচ্ছে না।"
    assert sink.lines[job_id][-1]["text_bn"] == job["error_bn"]


def test_runs_with_a_fake_model_and_never_a_real_one():
    seen = FakeModel("TAGGED")

    def tag(ctx):
        ctx.progress("Asking the model")
        return f"Done, {ctx.model.ask('tag these')}"
    r, sink = runner(model=seen)
    r.register("news_tag", tag)
    job_id = r.run(r.enqueue("news_tag", {"batch": "b1"}, asked_by="system"))
    assert seen.calls == ["tag these"] and sink.jobs[job_id]["result"] == "Done, TAGGED"


def test_a_model_job_without_a_model_fails_plainly_instead_of_spending_usage():
    r, sink = runner(model=None)
    r.register("analyse", lambda ctx: ctx.model.ask("x"))
    job_id = r.run(r.enqueue("analyse", {"symbol": "FIXA", "exchange": "NSE"}, asked_by="father"))
    assert sink.jobs[job_id]["status"] == "failed"
    assert "model" in sink.jobs[job_id]["error"].lower()


def test_kinds_and_payload_keys_come_from_the_contract():
    r, _ = runner()
    with pytest.raises(jobrun.BadJob, match="unknown"):
        r.enqueue("make_coffee", {}, asked_by="owner")
    with pytest.raises(jobrun.BadJob, match="payload"):
        r.enqueue("analyse", {"symbol": "FIXA"}, asked_by="owner")          # exchange missing
    with pytest.raises(jobrun.BadJob, match="payload"):
        r.enqueue("sync", {"extra": 1}, asked_by="owner")
    with pytest.raises(jobrun.BadJob, match="asked_by"):
        r.enqueue("sync", {}, asked_by="stranger")


def test_a_kind_with_no_handler_fails_plainly():
    r, sink = runner()
    job_id = r.run(r.enqueue("backup", {}, asked_by="system"))
    assert sink.jobs[job_id]["status"] == "failed" and "not set up" in sink.jobs[job_id]["error"]


def test_secrets_never_reach_a_progress_line_or_the_result():
    def leaky(ctx):
        ctx.progress("token=abc123SECRET used")
        return "Done sk-ant-oat01-SECRETSECRET"
    r, sink = runner()
    r.register("sync", leaky)
    job_id = r.run(r.enqueue("sync", {}, asked_by="owner"))
    blob = json.dumps([sink.jobs[job_id], sink.lines[job_id]])
    assert "abc123SECRET" not in blob and "SECRETSECRET" not in blob


def test_write_time_trust_checks_refuse_bad_rows():
    sink = jobrun.MemorySink()
    sink.create_job({"id": "j1", "kind": "sync", "payload": {}, "asked_by": "owner", "status": "queued", "result": None,
                     "error": None, "error_bn": None, "created_at": "2026-11-25T09:15:00+05:30", "started_at": None,
                     "finished_at": None})
    line = {"job_id": "j1", "seq": 1, "at": "2026-11-25T09:15:00+05:30", "state": "info", "text": "A", "text_bn": None}
    sink.append_line(line)
    with pytest.raises(jobrun.TrustError, match="seq"):
        sink.append_line({**line, "seq": 3})                                    # a gap
    with pytest.raises(jobrun.TrustError, match="seq"):
        sink.append_line(dict(line))                                            # an edit of line 1
    with pytest.raises(jobrun.TrustError, match="at"):
        sink.append_line({**line, "seq": 2, "at": "2026-11-25T09:15:00Z"})      # not IST
    with pytest.raises(jobrun.TrustError, match="state"):
        sink.append_line({**line, "seq": 2, "state": "weird"})
    with pytest.raises(jobrun.TrustError, match="text"):
        sink.append_line({**line, "seq": 2, "text": "  "})
    with pytest.raises(jobrun.TrustError, match="status"):
        sink.update_job("j1", status="done-ish")
    sink.update_job("j1", status="running")
    with pytest.raises(jobrun.TrustError, match="status"):
        sink.update_job("j1", status="queued")                                  # no going back
    sink.update_job("j1", status="done", result="Done", finished_at="2026-11-25T09:16:00+05:30")
    with pytest.raises(jobrun.TrustError, match="status"):
        sink.update_job("j1", status="failed", error="late")                    # a finished job stays finished


def test_sqlite_sink_writes_the_real_d1_tables():
    db = sqlite3.connect(":memory:")
    for sql in sorted((ROOT / "web" / "migrations").glob("*.sql")):
        db.executescript(sql.read_text())
    sink = jobrun.SqliteSink(db)
    r = jobrun.JobRunner(sink, clock=Clock())
    r.register("sync", fixture_job)
    job_id = r.run(r.enqueue("sync", {}, asked_by="father"))
    status, result, payload = db.execute("select status, result, payload from jobs where id=?", [job_id]).fetchone()
    assert (status, result, payload) == ("done", "Done, 3 changes", "{}")
    rows = db.execute("select seq, state, text from job_lines where job_id=? order by seq", [job_id]).fetchall()
    assert rows == [(1, "info", "Logging in"), (2, "ok", "Logged in"), (3, "ok", "Done, 3 changes")]


def test_run_next_takes_the_oldest_queued_job():
    r, sink = runner()
    r.register("sync", fixture_job)
    a = r.enqueue("sync", {}, asked_by="owner")
    b = r.enqueue("sync", {}, asked_by="owner")
    assert r.run_next() == a and sink.jobs[b]["status"] == "queued"
    assert r.run_next() == b and r.run_next() is None


def test_legacy_job_runs_behind_the_entry_point():
    """A v1 tick job (`fn(m, now, force) -> dict`) moves behind the runner without being rewritten."""
    def old(m, now, force):
        return {"status": "ok", "rows": 7}
    r, sink = runner()
    r.register("nightly", jobrun.legacy(old, machine=object(), now=lambda: T0, say="Nightly run"))
    job_id = r.run(r.enqueue("nightly", {}, asked_by="system"))
    assert sink.jobs[job_id]["status"] == "done" and sink.jobs[job_id]["result"] == "Done, 7 rows"

    def old_failed(m, now, force):
        return {"status": "failed", "error": "Traceback boom"}
    r.register("nightly", jobrun.legacy(old_failed, machine=object(), now=lambda: T0, say="Nightly run"))
    job_id = r.run(r.enqueue("nightly", {}, asked_by="system"))
    assert sink.jobs[job_id]["status"] == "failed" and "Traceback" not in sink.jobs[job_id]["error"]
