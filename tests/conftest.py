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
