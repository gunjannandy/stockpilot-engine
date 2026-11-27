"""SKELETON-2: a Python row that breaks the JSON Schema fails its test."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "py"))

from stockpilot.io import RowInvalid, validate_row  # noqa: E402

GOOD = {"id": "r-1", "at": "2026-11-27T10:00:00+05:30", "source": "job"}


@pytest.fixture(scope="module", autouse=True)
def _schemas():
    subprocess.run(["pnpm", "gen"], cwd=ROOT, check=True, capture_output=True)


def test_a_good_ping_row_passes():
    validate_row("ping", GOOD)


@pytest.mark.parametrize("bad", [{**GOOD, "at": "2026-11-27"}, {**GOOD, "source": "x"}, {"id": "r-1"}, {**GOOD, "n": 1}])
def test_a_row_that_breaks_the_schema_fails(bad):
    with pytest.raises(RowInvalid):
        validate_row("ping", bad)
