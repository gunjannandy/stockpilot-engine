import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops/orchestrator/tests"))
from orch_helpers import *  # noqa: E402,F401,F403
import dispatch  # noqa: E402
import pace  # noqa: E402
import buildstatus  # noqa: E402


def test_due_private_run_plans_one_session_in_private():
    runs = [{"check": "C-77-1", "ticket": "A", "due_at": ago(5), "claimed_by": None},
            {"check": "C-77-2", "ticket": "A", "due_at": ago(-60), "claimed_by": None},
            {"check": "C-77-3", "ticket": "A", "due_at": ago(5), "claimed_by": "primary"}]
    p = dispatch.plan(world([], private_runs=runs))
    assert len(p["private_runs"]) == 1
    r = p["private_runs"][0]
    assert (r["check"], r["environment"], r["prompt_file"], r["model"]) == \
        ("C-77-1", "private", "docs/spec/v3/private-run.md", "sonnet")
    live = [session("pr1", "A", kind="private-run", check="C-77-1")]
    assert dispatch.plan(world([], live, private_runs=runs))["private_runs"] == []


def test_trace_copy_differing_from_private_plans_a_sync_pr_once():
    w = world([], trace={"engine": "a\n", "private": "a\nb\n", "open_pr": False})
    assert dispatch.plan(w)["sync_trace"] == {"branch": "lane/trace-sync", "reason": "engine copy differs"}
    w["trace"]["open_pr"] = True
    assert dispatch.plan(w)["sync_trace"] is None
    same = world([], trace={"engine": "a\r\nb\r\n", "private": "a\nb\n", "open_pr": False})
    assert dispatch.plan(same)["sync_trace"] is None


def test_sync_trace_opens_a_pr_through_the_runner():
    calls = []
    dispatch.sync_trace(engine_csv="a\n", private_csv="a\nb\n", runner=lambda *a, **k: calls.append((a, k)) or {"number": 5})
    verbs = [c[0][0] for c in calls]
    assert verbs == ["branch", "put_file", "open_pr"]
    assert calls[1][1]["content"] == "a\nb\n" and calls[1][1]["path"] == "checks/trace.csv"
    assert "Refs stockpilot-hq/stockpilot#138" in calls[2][1]["body"]
