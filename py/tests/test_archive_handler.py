"""The archive Job has a `run(ctx)` handler, so the runtime (and archive.yml) can start it."""
import io
from datetime import date

from stockpilot.jobs import archive
from stockpilot.runtime.entry import load_handler
from stockpilot.runtime.progress import Progress


class Ctx:
    def __init__(self):
        self.progress = Progress("archive-1", io.StringIO())
        self.range = type("R", (), {"end": date(2026, 11, 28)})()


def test_the_runtime_finds_the_archive_handler():
    assert load_handler("archive") is archive.run


def test_nothing_registered_means_nothing_moved():
    assert archive.run(Ctx(), tables={}) == "nothing to archive: no table is past the archive age"


def test_old_rows_move_then_are_deleted(tmp_path):
    deleted = []
    rows = [{"day": "2024-01-01", "body": "old"}, {"day": "2026-11-01", "body": "new"}]
    src = type("S", (), {"read": lambda self, t: rows, "delete": lambda self, t, r: deleted.extend(r)})()
    out = archive.run(Ctx(), tables={"runs": src}, out_dir=tmp_path)
    assert out == "archived 1 rows from 1 tables"
    assert [r["body"] for r in deleted] == ["old"]
    assert list(tmp_path.glob("runs-*.parquet"))
