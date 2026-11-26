"""V2: the Sync job. The Kite callback creates it; the VM reads holdings with the day's token and says each step."""
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from fake_worker import KEY, FakeWorker
from stockpilot import jobrun, store
from stockpilot.jobs import minute, sync
from stockpilot.sources import kite

IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 11, 26, 9, 15, tzinfo=IST)
ROOT = Path(__file__).parents[2]

BASE = {"holdings": [{"tradingsymbol": "AAA", "isin": "INE000A01010", "quantity": 10, "t1_quantity": 0, "average_price": 100},
                     {"tradingsymbol": "BBB", "isin": "INE000B01010", "quantity": 5, "t1_quantity": 0, "average_price": 50}],
        "mf_holdings": [], "trades": [], "positions": {"net": [], "day": []}, "margins": {}, "gtts": []}
NEXT = {**BASE, "holdings": [{"tradingsymbol": "AAA", "isin": "INE000A01010", "quantity": 12, "t1_quantity": 0, "average_price": 100},
                             {"tradingsymbol": "CCC", "isin": "INE000C01010", "quantity": 3, "t1_quantity": 0, "average_price": 20}]}


def sync_job(i=1):
    return {"id": f"job_{i}", "kind": "sync", "payload": {}, "asked_by": "owner", "status": "queued", "result": None,
            "error": None, "error_bn": None, "created_at": "2026-11-26T09:10:00+05:30", "started_at": None, "finished_at": None}


class Source:
    def __init__(self, queued): self.queued = queued
    def pending(self): return {"queued": self.queued, "last_nightly": "2026-11-26T02:00:00+05:30"}


def run_tick(tmp_path, payloads):
    """Fire the minute check once per payload against one database; returns (sink-per-fire, db)."""
    db = store.open(tmp_path / "sp.duckdb")
    sinks = []
    for n, payload in enumerate(payloads, 1):
        worker = FakeWorker(kite=payload)
        try:
            sink = jobrun.MemorySink()
            minute.tick(Source([sync_job(n)]), sink, make_backend=lambda name: None,
                        handlers={"sync": sync.handler(lambda: db, kite.Worker(worker.url, KEY))},
                        start_github=lambda j: None, alarm=lambda t: None, state={}, now=lambda: T0)
            sinks.append(sink)
        finally:
            worker.close()
    return sinks, db


def test_first_sync_shows_each_step_and_counts_every_holding_as_a_change(tmp_path):
    (sink,), db = run_tick(tmp_path, [BASE])
    job = sink.jobs["job_1"]
    assert job["status"] == "done" and job["result"] == "Done, 2 changes"
    assert [l["text"] for l in sink.lines["job_1"]] == ["Checking Kite login", "Logged in, holdings fetched", "Saving holdings", "Done, 2 changes"]
    assert [l["state"] for l in sink.lines["job_1"]] == ["info", "info", "info", "ok"]
    assert all(l["text_bn"] for l in sink.lines["job_1"][:-1])
    assert db.execute("select count(*) from holdings").fetchone()[0] == 2


def test_second_sync_counts_new_removed_and_resized_holdings(tmp_path):
    sinks, _ = run_tick(tmp_path, [BASE, NEXT])
    assert sinks[1].jobs["job_2"]["result"] == "Done, 3 changes"      # AAA 10 -> 12, BBB gone, CCC new


def test_unchanged_holdings_say_no_changes(tmp_path):
    sinks, _ = run_tick(tmp_path, [BASE, BASE])
    assert sinks[1].jobs["job_2"]["result"] == "Done, no changes"


def test_one_change_is_singular(tmp_path):
    one = {**BASE, "holdings": BASE["holdings"][:1] + [{**BASE["holdings"][1], "quantity": 6}]}
    sinks, _ = run_tick(tmp_path, [BASE, one])
    assert sinks[1].jobs["job_2"]["result"] == "Done, 1 change"


def test_no_kite_login_today_fails_in_plain_words_with_a_retry_path(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    worker = FakeWorker(kite=None)
    try:
        sink = jobrun.MemorySink()
        minute.tick(Source([sync_job()]), sink, make_backend=lambda n: None,
                    handlers={"sync": sync.handler(lambda: db, kite.Worker(worker.url, KEY))},
                    start_github=lambda j: None, alarm=lambda t: None, state={}, now=lambda: T0)
    finally:
        worker.close()
    job = sink.jobs["job_1"]
    assert job["status"] == "failed" and "Press Sync" in job["error"] and job["error_bn"]
    assert sink.lines["job_1"][-1]["state"] == "fail"
    assert db.execute("select count(*) from holdings").fetchone()[0] == 0


def test_sync_is_a_vm_private_kind_the_tick_picks_up():
    assert jobrun.CONTRACT["job_kinds"]["sync"]["runs_on"] == "vm_private"


def test_no_order_endpoint_is_ever_called(tmp_path):
    seen = []
    class Spy(kite.Worker):
        def request(self, method, path, body=None):
            seen.append((method, path))
            return 200, BASE
    db = store.open(tmp_path / "sp.duckdb")
    sink = jobrun.MemorySink()
    minute.tick(Source([sync_job()]), sink, make_backend=lambda n: None, handlers={"sync": sync.handler(lambda: db, Spy("http://x", KEY))},
                start_github=lambda j: None, alarm=lambda t: None, state={}, now=lambda: T0)
    assert seen == [("GET", "/api/vm/kite")]
    source = (ROOT / "src/stockpilot/jobs/sync.py").read_text()
    assert not re.search(r"/orders|place_order|/gtt/triggers.*POST|\"POST\"", source)
