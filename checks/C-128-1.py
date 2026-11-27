"""C-128-1: rows past the archive age move to Parquet and leave D1."""
import sys
from datetime import date
from pathlib import Path

import duckdb

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "py"))
from stockpilot.jobs.archive import archive  # noqa: E402


def test_old_rows_move_to_parquet_and_are_deleted_after(tmp_path):
    rows = [{"day": "2024-01-01", "body": "a"}, {"day": "2024-02-01", "body": "b"}, {"day": "2026-11-01", "body": "c"}]
    deleted = []

    def delete(batch):
        deleted.extend(batch)

    out = archive("calls", rows, tmp_path, date(2026, 11, 28), delete)
    assert out["moved"] == 2 and len(deleted) == 2
    assert duckdb.connect().execute(f"select count(*) from read_parquet('{out['file']}')").fetchone()[0] == 2
    assert all(r["day"] < "2025" for r in deleted)


def test_nothing_old_means_no_file_and_no_delete(tmp_path):
    out = archive("calls", [{"day": "2026-11-01", "body": "c"}], tmp_path, date(2026, 11, 28), lambda b: 1 / 0)
    assert out == {"moved": 0, "file": None}


def test_a_failed_write_deletes_nothing(tmp_path):
    bad = tmp_path / "file-not-dir"
    bad.write_text("x")
    try:
        archive("calls", [{"day": "2020-01-01", "body": "x"}], bad, date(2026, 11, 28), lambda b: 1 / 0)
    except (OSError, ZeroDivisionError) as e:
        assert not isinstance(e, ZeroDivisionError)
