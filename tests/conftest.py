"""Fixtures shared by several test files; a file that needs something different defines its own `db`."""
import pytest

from stockpilot import store


@pytest.fixture
def db(tmp_path):
    return store.open(tmp_path / "sp.duckdb")


@pytest.fixture(autouse=True)
def _ship_does_not_run_the_real_verify(monkeypatch, request):
    """`ship.ship` runs `sp verify` twice (lane P2). A test of something else must not run the real checks against a toy store;
    tests/jobs/test_ship_verify.py is left alone and sets its own."""
    if request.module.__name__.endswith("test_ship_verify"):
        return
    from stockpilot.jobs import ship
    monkeypatch.setattr(ship, "run_verify", lambda m, day, *, write=True: {"hard_failed": 0, "summary": "stubbed"})


# Tests that read the private tree (ops/, docs/, .github/), which the public code copy does not carry (publish.py allow list).
# In the private repo they all run; in the public copy they skip with this message instead of failing.
_NEEDS_PRIVATE_TREE = (
    "tests/test_ops.py", "tests/test_wrangler_path.py", "tests/test_heartbeat.py", "tests/test_publish.py::test_public_workflows_exist",
    "tests/test_publish.py::test_keep_alive_is_scheduled", "tests/jobs/test_vmjobs.py::test_the_timer_unit_is_a_oneshot",
    "tests/sources/test_history.py::test_public_workflows_parse", "tests/verify/test_model_checks.py::test_the_real_baseline_table",
    "tests/jobs/test_modelfix.py::test_the_batch_is_small_and_the_worst_case_job_fits_inside_the_unit_timeout",
    "tests/test_publish.py::test_data_jobs_no_longer_live_in_the_private_workflows_folder",
)


def pytest_collection_modifyitems(config, items):
    root = config.rootpath
    if (root / "ops").is_dir() and (root / "docs").is_dir():
        return
    skip = pytest.mark.skip(reason="needs ops/ and docs/, which are not in the public code copy")
    for item in items:
        if item.nodeid.startswith(_NEEDS_PRIVATE_TREE):
            item.add_marker(skip)
