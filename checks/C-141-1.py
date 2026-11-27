"""C-141-1: the never-order check runs on every PR (and in the merge queue), and `gate` needs it."""
from pathlib import Path

import yaml

CI = yaml.safe_load((Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml").read_text())
ON = CI[True]


def test_ci_runs_on_every_pull_request_with_no_path_filter():
    assert "pull_request" in ON and not (ON["pull_request"] or {}).get("paths") and not (ON["pull_request"] or {}).get("branches")
    assert "merge_group" in ON


def test_a_never_order_job_exists_runs_unconditionally_and_gates_main():
    job = CI["jobs"]["never-order"]
    assert "if" not in job
    assert "never-order" in " ".join(s.get("run", "") for s in job["steps"])
    assert "never-order" in CI["jobs"]["gate"]["needs"]
