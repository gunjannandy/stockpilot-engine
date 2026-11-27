import io
import json
from datetime import date

import pytest
from fake_runtime_worker import KEY, FakeRuntimeWorker

from stockpilot.io import Door
from stockpilot.runtime import JobRefused, parse_range, row_id, run_job, stable_rows
from stockpilot.runtime.progress import Progress


def door(worker):
    return Door("https://x.invalid", KEY, worker.transport)


def test_range_defaults_to_the_day_and_checks_order():
    today = date(2026, 11, 27)
    assert str(parse_range(None, None, today)) == "2026-11-27..2026-11-27"
    assert str(parse_range("2026-11-20", None, today)) == "2026-11-20..2026-11-20"
    assert [d.day for d in parse_range("2026-11-25", "2026-11-27", today).days()] == [25, 26, 27]
    with pytest.raises(ValueError, match="before it starts"):
        parse_range("2026-11-27", "2026-11-20", today)
    with pytest.raises(ValueError, match="must be a day"):
        parse_range("27/11/2026", None, today)


def test_row_ids_depend_on_the_natural_key_only():
    assert row_id("holiday", "2026-12-25") == row_id("holiday", "2026-12-25")
    assert row_id("holiday", "2026-12-25") != row_id("holiday", "2026-12-26")
    rows = [{"id": "b", "n": 1}, {"id": "a", "n": 2}, {"id": "b", "n": 3}]
    assert stable_rows(rows) == [{"id": "a", "n": 2}, {"id": "b", "n": 3}]


def test_progress_lines_are_numbered_from_one_without_gaps():
    out = io.StringIO()
    p = Progress("r1", out)
    p.line("one")
    p.line("two", "ok")
    lines = [json.loads(x) for x in out.getvalue().splitlines()]
    assert [x["seq"] for x in lines] == [1, 2]
    assert lines[1]["state"] == "ok"
    with pytest.raises(ValueError):
        p.line("bad", "maybe")


def test_a_job_begins_publishes_and_ends():
    w = FakeRuntimeWorker()
    out = io.StringIO()

    def handler(ctx):
        ctx.publish("calendar", [{"id": "x", "kind": "holiday"}], source="test", as_of="2026-11-27")
        return "ok then"

    run_id = run_job("calendar", handler, door=door(w), day="2026-11-27", out=out)
    assert w.runs["calendar|all|2026-11-27"]["status"] == "done"
    assert w.runs["calendar|all|2026-11-27"]["run_id"] == run_id
    assert list(w.rows["calendar"]) == ["x"]
    assert [json.loads(x)["seq"] for x in out.getvalue().splitlines()] == [1, 2, 3]
    assert "usually about 12 seconds" in out.getvalue()


def test_a_failing_handler_ends_the_job_failed_and_raises():
    w = FakeRuntimeWorker()

    def handler(ctx):
        raise RuntimeError("source down")

    with pytest.raises(RuntimeError, match="source down"):
        run_job("calendar", handler, door=door(w), day="2026-11-27", out=io.StringIO())
    row = w.runs["calendar|all|2026-11-27"]
    assert (row["status"], row["error"]) == ("failed", "source down")


def test_a_refused_begin_runs_nothing():
    w = FakeRuntimeWorker()
    w.refuse_begin = (423, "locked: another calendar Job is running")
    ran = []
    with pytest.raises(JobRefused) as err:
        run_job("calendar", lambda ctx: ran.append(1), door=door(w), day="2026-11-27", out=io.StringIO())
    assert err.value.status == 423 and ran == []


def test_a_second_identical_job_is_refused_and_a_rerun_leaves_the_same_rows():
    w = FakeRuntimeWorker()
    rows = [{"id": row_id("h", "2026-12-25"), "kind": "holiday"}, {"id": row_id("h", "2026-12-26"), "kind": "holiday"}]

    def handler(ctx):
        ctx.publish("calendar", rows + rows[:1], source="test")   # a duplicate row in the batch is sent once

    run_job("calendar", handler, door=door(w), day="2026-11-27", start="2026-11-20", end="2026-11-27", out=io.StringIO())
    first = dict(w.rows["calendar"])
    with pytest.raises(JobRefused):
        run_job("calendar", handler, door=door(w), day="2026-11-27", out=io.StringIO())
    run_job("calendar", handler, door=door(w), day="2026-11-27", start="2026-11-20", end="2026-11-27", rerun=True, out=io.StringIO())
    assert w.rows["calendar"] == first and len(first) == 2
