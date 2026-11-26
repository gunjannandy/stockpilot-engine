"""QUEUE (#115): the D1 views portfolio, smallcase and own_record are written after every sync and every build."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fake_worker import KEY, FakeWorker
from test_sync_job import BASE, NEXT, Source, sync_job
from test_wire import d1
from stockpilot import jobrun, store, views
from stockpilot.jobs import minute, sync
from stockpilot.sources import kite

IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 11, 26, 9, 15, tzinfo=IST)
AT = "2026-11-26T09:15:00+05:30"


def stored(query, name):
    rows = query("select * from views where name = ?", [name])
    return (rows[0]["as_of"], rows[0]["written_at"], json.loads(rows[0]["doc"])) if rows else None


def test_build_from_the_store_gives_the_three_views_with_as_of_and_written_at(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    kite.store_payload(db, BASE)
    _, query = d1()
    got = views.write_from_store(db, query, date(2026, 11, 26), AT, default_budget=100000, previous={})
    assert got == ["portfolio", "smallcase", "own_record"]
    as_of, written, doc = stored(query, "portfolio")
    assert written == AT and as_of == "2026-11-26"
    assert {h["symbol"] for h in doc["holdings"]} == {"AAA", "BBB"}
    assert doc["budget"]["month"] == "2026-11"
    assert stored(query, "smallcase")[1] == AT and stored(query, "own_record")[1] == AT
    assert stored(query, "own_record")[2]["as_of"]


def test_a_second_write_replaces_the_row_and_keeps_the_reasoning_the_last_build_attached(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    kite.store_payload(db, BASE)
    _, query = d1()
    first = {"holdings": [{"symbol": "AAA", "reasoning": {"why": "kept"}}], "budget": {"month": "2026-11", "total": 5, "planned": 2, "left": 3}}
    views.write_from_store(db, query, date(2026, 11, 26), AT, 100000, previous={"portfolio": first})
    doc = stored(query, "portfolio")[2]
    assert [h.get("reasoning") for h in doc["holdings"] if h["symbol"] == "AAA"] == [{"why": "kept"}]
    assert doc["budget"]["planned"] == 2                      # the build knows the planned buys; a sync does not
    kite.store_payload(db, NEXT)
    views.write_from_store(db, query, date(2026, 11, 26), "2026-11-26T10:00:00+05:30", 100000, previous={"portfolio": doc})
    assert query("select count(*) n from views where name = 'portfolio'")[0]["n"] == 1
    assert {h["symbol"] for h in stored(query, "portfolio")[2]["holdings"]} == {"AAA", "CCC"}
    assert stored(query, "portfolio")[1] == "2026-11-26T10:00:00+05:30"


def test_write_from_a_built_site_copies_the_three_files_the_page_already_gets(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "portfolio.json").write_text(json.dumps({"snapshot_at": "2026-11-25 18:00:00", "holdings": []}))
    (data / "smallcase.json").write_text(json.dumps({"as_of": "2026-11-25", "lines": []}))
    (data / "own_record.json").write_text(json.dumps({"as_of": "2026-11-24", "closed": 0}))
    _, query = d1()
    assert views.write_from_site(tmp_path, query, AT, date(2026, 11, 26)) == ["portfolio", "smallcase", "own_record"]
    assert stored(query, "portfolio")[:2] == ("2026-11-25", AT)
    assert stored(query, "own_record")[0] == "2026-11-24"
    (data / "smallcase.json").unlink()
    assert views.write_from_site(tmp_path, query, AT, date(2026, 11, 26)) == ["portfolio", "own_record"]     # a missing file leaves its row alone


def test_the_sync_job_updates_the_views_before_it_says_done(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    _, query = d1()
    worker = FakeWorker(kite=BASE)
    try:
        sink = jobrun.MemorySink()
        publish = lambda d: views.write_from_store(d, query, date(2026, 11, 26), AT, 100000, views.previous(query))
        minute.tick(Source([sync_job()]), sink, make_backend=lambda n: None,
                    handlers={"sync": sync.handler(lambda: db, kite.Worker(worker.url, KEY), publish_views=publish)},
                    start_github=lambda j: None, alarm=lambda t: None, state={}, now=lambda: T0)
    finally:
        worker.close()
    lines = [l["text"] for l in sink.lines["job_1"]]
    assert lines[-3:] == ["Saving holdings", "Updating Holdings, Tax and Our record", "Done, 2 changes"]
    assert sink.jobs["job_1"]["status"] == "done" and stored(query, "portfolio")


def test_a_views_failure_does_not_undo_a_sync(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    worker = FakeWorker(kite=BASE)
    try:
        sink = jobrun.MemorySink()
        def boom(d): raise RuntimeError("D1 down")
        minute.tick(Source([sync_job()]), sink, make_backend=lambda n: None,
                    handlers={"sync": sync.handler(lambda: db, kite.Worker(worker.url, KEY), publish_views=boom)},
                    start_github=lambda j: None, alarm=lambda t: None, state={}, now=lambda: T0)
    finally:
        worker.close()
    assert sink.jobs["job_1"]["status"] == "done" and "Holdings are saved" in sink.jobs["job_1"]["result"]
    assert db.execute("select count(*) from holdings").fetchone()[0] == 2


def test_ship_writes_the_views_after_a_build_and_never_stops_the_ship(tmp_path):
    from stockpilot.jobs import ship
    data = tmp_path / "data"
    data.mkdir()
    (data / "portfolio.json").write_text(json.dumps({"snapshot_at": "2026-11-25", "holdings": []}))
    _, query = d1()
    assert ship.write_views(None, tmp_path, T0, query=query) == "wrote portfolio"
    assert stored(query, "portfolio")[1] == AT
    def broken(sql, params=()): raise RuntimeError("D1 down")
    assert ship.write_views(None, tmp_path, T0, query=broken) == "failed: RuntimeError"
