"""MOVE-2: py CI collects py/tests and ops/orchestrator/tests; no v2 workflow can run; `gate` needs every job."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
CI = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text())


def test_only_the_allowed_workflows_are_in_github_workflows():
    allowed = {"ci.yml", "promote.yml", "calendar.yml", "_job.yml", "archive.yml", "funds.yml", "fundholdings.yml", "facts.yml", "history.yml", "universe.yml", "usprices.yml", "dividends.yml"}
    found = {p.name for p in (ROOT / ".github/workflows").glob("*.yml")}
    assert {"ci.yml", "promote.yml"} <= found <= allowed


def test_ci_keeps_the_merge_group_trigger():
    assert "merge_group" in CI[True]          # PyYAML reads the key `on` as True


def test_gate_needs_every_other_job_and_stays_red_on_a_skip():
    jobs = CI["jobs"]
    assert set(jobs["gate"]["needs"]) == set(jobs) - {"gate"}
    assert "skipped" in jobs["gate"]["steps"][0]["run"]


def test_py_job_runs_xdist_over_py_tests_and_the_orchestrator_tests_and_fits_in_five_minutes():
    py = CI["jobs"]["py"]
    text = "\n".join(s.get("run", "") for s in py["steps"])
    assert "py/tests" in text and "ops/orchestrator/tests" in text and "-n auto" in text
    assert py["timeout-minutes"] <= 5


def test_ts_job_is_node_24():
    assert any(s.get("with", {}).get("node-version") == 24 for s in CI["jobs"]["ts"]["steps"])
