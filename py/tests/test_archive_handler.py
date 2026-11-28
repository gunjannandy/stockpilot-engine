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


def test_d1_table_reads_old_rows_and_deletes_by_key():
    import json
    from stockpilot.jobs.archive.d1table import D1Table, from_env
    from stockpilot.jobs.backup.d1 import D1
    sent = []

    def post(url, headers, body):
        q = json.loads(body)
        sent.append(q)
        rows = [{"id": "e1", "at": "2024-01-02T10:00:00+05:30", "message": "x", "_day": "2024-01-02"}]
        return {"success": True, "result": [{"results": rows if q["sql"].startswith("select") else []}]}

    t = D1Table(D1("a", "d", "tok", post), "substr(at, 1, 10)", "id", 400)
    rows = t.read("browser_errors")
    assert rows[0]["day"] == "2024-01-02" and rows[0]["key"] == "e1" and "_day" not in rows[0]["body"]
    assert sent[0]["params"] == ["-400 day"]
    t.delete("browser_errors", rows)
    assert sent[1]["sql"].startswith('delete from "browser_errors"') and sent[1]["params"] == ["e1"]
    assert from_env({}) == {}
    assert set(from_env({"CF_ACCOUNT_ID": "a", "D1_PRODUCTION_ID": "d", "CF_D1_ARCHIVE_TOKEN": "t"})) == {"browser_errors"}
