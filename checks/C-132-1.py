"""C-132-1: a workflow with any trigger other than workflow_dispatch fails; the models environment is main-only."""
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from gates import workflow_triggers as wt  # noqa: E402


def wf(on, jobs=None):
    return yaml.safe_load(yaml.safe_dump({"on": on, "jobs": jobs or {"a": {"runs-on": "x"}}}))


def check(files):
    return wt.check({name: yaml.safe_dump(doc) for name, doc in files.items()})


def test_dispatch_only_passes_in_every_spelling():
    for on in ("workflow_dispatch", ["workflow_dispatch"], {"workflow_dispatch": None}, {"workflow_dispatch": {"inputs": {}}}):
        assert check({"x.yml": wf(on)}) == []


def test_any_other_trigger_fails():
    for on in ("push", ["workflow_dispatch", "schedule"], {"workflow_dispatch": None, "pull_request": {}}, {"schedule": [{"cron": "0 0 * * *"}]}, {"workflow_run": {}}):
        assert check({"x.yml": wf(on)}), on


def test_ci_and_promote_are_exempt_but_other_names_are_not():
    assert check({"ci.yml": wf({"push": {}}), "promote.yml": wf({"push": {}})}) == []
    assert check({"ci.yaml": wf({"push": {}})})


def test_models_environment_must_be_guarded_to_main():
    bad = wf("workflow_dispatch", {"m": {"runs-on": "x", "environment": "models"}})
    ok = wf("workflow_dispatch", {"m": {"runs-on": "x", "environment": {"name": "models"}, "if": "github.ref == 'refs/heads/main'"}})
    assert check({"x.yml": bad}) and check({"x.yml": ok}) == []


def test_ci_itself_may_not_touch_models():
    assert check({"ci.yml": wf({"push": {}}, {"m": {"runs-on": "x", "environment": "models"}})})


def test_this_repo_passes():
    root = Path(__file__).resolve().parents[1]
    assert wt.check_dir(root / ".github/workflows") == []


def test_the_reusable_job_workflow_may_only_be_called():
    assert check({"_job.yml": wf({"workflow_call": {}})}) == []
    assert check({"_job.yml": wf("workflow_dispatch")})
    assert check({"x.yml": wf({"workflow_call": {}})})
