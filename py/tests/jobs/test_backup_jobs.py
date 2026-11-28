"""The D1 backup and drill Jobs: fake source and target, a local bare git repo as the vault; no network."""
import subprocess
from datetime import datetime, timedelta, timezone

import pytest

from stockpilot import vault
from stockpilot.jobs import backup as job

IST = timezone(timedelta(hours=5, minutes=30))
PASSWORD = "correct horse battery"


@pytest.fixture(scope="module")
def keys():
    return vault.create_keys(PASSWORD)


@pytest.fixture
def remote(tmp_path):
    path = tmp_path / "vault.git"
    subprocess.run(["git", "init", "-q", "--bare", str(path)], check=True)
    return str(path)


class FakeD1:
    def __init__(self, data):
        self.data = {t: [dict(r) for r in rows] for t, rows in data.items()}

    def tables(self):
        return list(self.data)

    def pages(self, table, size=2):
        rows = self.data[table]
        for i in range(0, len(rows), size):
            yield rows[i:i + size]

    def replace(self, table, rows):
        self.data[table] = [dict(r) for r in rows]

    def count(self, table):
        return len(self.data[table]) if table in self.data else None


DATA = {"calls": [{"id": 1, "symbol": "AAA"}, {"id": 2, "symbol": "BBB"}, {"id": 3, "symbol": "CCC"}],
        "watchlist": [{"symbol": "AAA", "note": None}], "empty": []}


class Sink:
    def __init__(self):
        self.reports, self.beats = [], []

    def report(self, body):
        self.reports.append(body)

    def beat(self, part, ok, error=None):
        self.beats.append((part, ok, error))


def test_backup_then_drill_round_trips_counts_and_checksums(tmp_path, remote, keys):
    out = Sink()
    got = job.backup(FakeD1(DATA), remote, keys, tmp_path / "w1", out.report, out.beat)
    assert got == {"calls": 3, "watchlist": 1, "empty": 0}
    assert out.beats == [("job.backup", True, None)]
    assert out.reports[0]["kind"] == "backup" and out.reports[0]["ok"] is True
    assert out.reports[0]["tables"]["calls"]["rows"] == 3

    target = FakeD1({t: [] for t in DATA})
    drill = Sink()
    result = job.drill(target, remote, PASSWORD, tmp_path / "w2", drill.report, drill.beat)
    assert result == {"ok": True, "tables": {"calls": 3, "watchlist": 1, "empty": 0}}
    assert target.data == DATA                       # None survives as null
    assert drill.beats == [("job.drill", True, None)]
    assert drill.reports[0]["kind"] == "drill" and drill.reports[0]["ok"] is True


def test_drill_names_the_table_whose_count_is_wrong_and_beats_red(tmp_path, remote, keys):
    job.backup(FakeD1(DATA), remote, keys, tmp_path / "w1", Sink().report, Sink().beat)

    class Lossy(FakeD1):
        def replace(self, table, rows):
            super().replace(table, rows[:-1] if table == "calls" else rows)

    sink = Sink()
    with pytest.raises(job.DrillError, match="calls"):
        job.drill(Lossy({t: [] for t in DATA}), remote, PASSWORD, tmp_path / "w2", sink.report, sink.beat)
    assert sink.beats[0][:2] == ("job.drill", False)
    assert sink.reports[0]["ok"] is False and "calls" in sink.reports[0]["detail"]


def test_drill_refuses_a_table_missing_from_the_target(tmp_path, remote, keys):
    job.backup(FakeD1(DATA), remote, keys, tmp_path / "w1", Sink().report, Sink().beat)
    sink = Sink()
    with pytest.raises(job.DrillError, match="watchlist"):
        job.drill(FakeD1({"calls": [], "empty": []}), remote, PASSWORD, tmp_path / "w2", sink.report, sink.beat)


def test_a_failed_backup_beats_red_and_pushes_nothing(tmp_path, remote, keys):
    class Broken(FakeD1):
        def pages(self, table, size=2):
            raise RuntimeError("D1 said 500")

    sink = Sink()
    with pytest.raises(RuntimeError):
        job.backup(Broken(DATA), remote, keys, tmp_path / "w", sink.report, sink.beat)
    assert sink.beats == [("job.backup", False, "D1 said 500")]
    assert not (tmp_path / "w").exists()             # plaintext never outlives the call


def test_work_folder_is_deleted_after_a_good_backup(tmp_path, remote, keys):
    job.backup(FakeD1(DATA), remote, keys, tmp_path / "w", Sink().report, Sink().beat)
    assert not (tmp_path / "w").exists()


def test_internal_tables_are_not_backed_up():
    assert not job.wanted("sqlite_sequence") and not job.wanted("_cf_KV") and not job.wanted("d1_migrations")
    assert job.wanted("calls")


def test_next_due_windows():
    now = datetime(2026, 11, 28, 2, 0, tzinfo=IST)
    assert job.DUE["job.backup"] == timedelta(days=1, hours=2)
    assert job.DUE["job.drill"] > timedelta(days=31)
    assert now.tzinfo is not None


def test_d1_rest_client_pages_and_quotes():
    import json as j

    from stockpilot.jobs.backup.d1 import D1
    sent = []

    def post(url, headers, body):
        q = j.loads(body)
        sent.append(q)
        rows = [{"a": 1}, {"a": 2}] if "offset 0" in q["sql"] else []
        return {"success": True, "result": [{"results": rows}]}

    d1 = D1("acct", "db", "tok", post)
    assert [len(p) for p in d1.pages('we"ird')] == [2]
    assert '"we""ird"' in sent[0]["sql"]
    d1.replace("calls", [{"id": 1, "note": None}])
    assert sent[-1]["sql"] == 'insert into "calls" ("id", "note") values (?, ?)' and sent[-1]["params"] == [1, None]
    with pytest.raises(RuntimeError):
        D1("a", "d", "t", lambda *_: {"success": False, "errors": ["no"]}).tables()
