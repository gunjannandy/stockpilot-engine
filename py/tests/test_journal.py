"""The journal: run rows and problem rows, the one place jobs record what happened."""
import pytest

from stockpilot import journal, store


@pytest.fixture
def db(tmp_path):
    return store.open(tmp_path / "t.duckdb")


def problems(db):
    return db.execute("select job, severity, message, count, resolution from problems order by id").fetchall()


def test_a_repeated_warning_is_one_row_with_a_count(db):
    for _ in range(3):
        journal.problem(db, "trades", "INE002A01018: the statement shows 10, the lots hold 8.")
    assert problems(db) == [("trades", "warning", "INE002A01018: the statement shows 10, the lots hold 8.", 3, None)]


def test_a_key_groups_warnings_whose_wording_changes(db):
    journal.problem(db, "kite", "TCS: Kite holds 10, lots say 8.", key="mismatch:TCS")
    journal.problem(db, "kite", "TCS: Kite holds 11, lots say 8.", key="mismatch:TCS")
    assert problems(db) == [("kite", "warning", "TCS: Kite holds 11, lots say 8.", 2, None)]


def test_a_resolved_problem_that_comes_back_is_a_new_row(db):
    journal.problem(db, "deploy", "deploy: wrangler exited 1", severity="error")
    db.execute("update problems set resolution = 'cleared'")
    journal.problem(db, "deploy", "deploy: wrangler exited 1", severity="error")
    assert [p[3:] for p in problems(db)] == [(1, "cleared"), (1, None)]


def test_a_run_records_ok_with_its_notes(db):
    with journal.run(db, "nav") as run:
        run.notes["navs"] = 12
    assert db.execute("select job, status, notes->>'navs' from runs").fetchone() == ("nav", "ok", "12")


def test_a_run_can_end_partial_or_holiday(db):
    with journal.run(db, "weekly") as run:
        run.status = "partial"
    assert db.execute("select status from runs").fetchone() == ("partial",)


def test_a_run_that_raises_is_failed_logs_an_error_and_reraises(db):
    with pytest.raises(RuntimeError):
        with journal.run(db, "queue"):
            raise RuntimeError("Worker queue answered 500")
    assert db.execute("select status, notes->>'error' from runs").fetchone() == ("failed", "Worker queue answered 500")
    assert problems(db)[0][:2] == ("queue", "error")


# ---- R16: one-time cleanup of old problems -------------------------------------------------------------------

def _redo_last_migration(tmp_path, seed):
    """Seed the table, then run the problems-cleanup migration's SQL on those rows. It is found by its text, not by
    position: later lanes append migrations after it, and the store only applies versions newer than the latest."""
    from stockpilot import store
    db = store.open(tmp_path / "old.duckdb")
    seed(db)
    sql = next(m for m in store.MIGRATIONS if "delete from problems where resolution is not null" in m)
    db.execute(sql)
    return db


def _rows(db):
    return db.execute("select job, key, message, resolution, count from problems order by id").fetchall()


def test_cleanup_merges_unresolved_duplicates_and_drops_old_resolved_rows(tmp_path):
    def seed(db):
        ins = ("insert into problems (seen_at, last_seen, job, severity, message, key, count, resolution) "
               "values (current_timestamp - interval '{age} day', current_timestamp - interval '{age} day', ?, 'error', ?, ?, ?, ?)")
        for _ in range(3):                                               # three copies of one unresolved problem
            db.execute(ins.format(age=40), ["deploy", "deploy: x", "deploy: x", 1, None])
        db.execute(ins.format(age=5), ["deploy", "deploy: x", "deploy: x", 2, None])
        db.execute(ins.format(age=2), ["nav", "nav: y", "nav: y", 1, None])        # unresolved and recent, alone
        db.execute(ins.format(age=45), ["doctor", "old-key", "old-key", 1, "cleared"])   # resolved and old: dropped
        db.execute(ins.format(age=10), ["doctor", "new-key", "new-key", 1, "cleared"])   # resolved but recent: kept
        db.execute(ins.format(age=90), ["tick", "t", "t", 1, "fixed"])                   # resolved and old: dropped
        db.execute(ins.format(age=90), ["tick", "t", "t", 1, None])                      # unresolved and old: KEPT
    db = _redo_last_migration(tmp_path, seed)
    rows = _rows(db)
    unresolved_deploy = [r for r in rows if r[0] == "deploy"]
    assert len(unresolved_deploy) == 1 and unresolved_deploy[0][4] == 5          # 1+1+1+2 occurrences, one row
    assert [r for r in rows if r[0] == "nav"] and [r for r in rows if r[1] == "new-key"]
    assert not [r for r in rows if r[1] == "old-key"]
    assert [r[3] for r in rows if r[0] == "tick"] == [None]                       # the resolved one went, the open one stayed
    first = db.execute("select min(seen_at) from problems where job = 'deploy'").fetchone()[0]
    assert (db.execute("select current_timestamp::timestamp").fetchone()[0] - first).days >= 39    # earliest sighting kept


def test_cleanup_is_idempotent_and_never_touches_distinct_problems(tmp_path):
    def seed(db):
        for msg in ("a", "b"):
            db.execute("insert into problems (job, severity, message, key) values ('x', 'error', ?, ?)", [msg, msg])
        db.execute("insert into problems (job, severity, message) values ('x', 'error', 'no key 1')")     # no key: by message
        db.execute("insert into problems (job, severity, message) values ('x', 'error', 'no key 2')")
    db = _redo_last_migration(tmp_path, seed)
    before = _rows(db)
    assert len(before) == 4
    from stockpilot import store
    version = next(i for i, m in enumerate(store.MIGRATIONS, 1) if "delete from problems where resolution is not null" in m)
    db.execute("delete from schema_migrations where version = ?", [version])
    path = [p for (p,) in db.execute("select path from duckdb_databases() where not internal and path is not null").fetchall()][0]
    db.close()
    assert _rows(store.open(path)) == before


def test_prune_resolved_drops_old_resolved_rows_only(db):
    db.execute("insert into problems (job, severity, message, key, resolution, count, seen_at, last_seen) values "
               "('a', 'warning', 'old done', 'k1', 'cleared', 1, current_timestamp - interval 40 day, current_timestamp - interval 40 day), "
               "('a', 'warning', 'new done', 'k2', 'cleared', 1, current_timestamp - interval 3 day, current_timestamp - interval 3 day), "
               "('a', 'warning', 'old open', 'k3', null, 1, current_timestamp - interval 90 day, current_timestamp - interval 90 day)")
    assert journal.prune_resolved(db) == 1
    assert {r[0] for r in db.execute("select key from problems").fetchall()} == {"k2", "k3"}
    assert journal.prune_resolved(db) == 0          # safe to run on every tick
