"""Shared fixtures for the verify tests: a small temp DB, built by hand, and a site built from the seeded fixture DB."""
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from stockpilot import store


@pytest.fixture
def db(tmp_path):
    return store.open(tmp_path / "v.duckdb")


