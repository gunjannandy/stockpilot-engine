"""Seam 3: the queue's heavy handlers, each crossing into another lane's code."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from fake_worker import KEY, FakeWorker
from fakes import queue_item
from stockpilot import config, site, store, vmqueue
from stockpilot.sources import kite
from stockpilot.jobs import docs, ship

FIX = Path(__file__).parent / "fixtures" / "trades"


def poll(db, queue, ctx):
    w = FakeWorker(queue=queue)
    try:
        vmqueue.poll(db, kite.Worker(w.url, KEY), ctx)
        return w.acks
    finally:
        w.close()


class Bridge:
    def list(self, since=None):
        return [{"id": "f1", "source": "drive", "name": "tradebook.csv"}]

    def file(self, ident):
        return SimpleNamespace(data=FIX.joinpath("tradebook.csv").read_bytes())


def test_refresh_docs_syncs_documents_then_rebuilds_lots_and_sales(db):
    ctx = vmqueue.Context(sync_docs=lambda d: docs.sync_docs(d, Bridge(), "PAN"))
    [ack] = poll(db, [queue_item("001", "refresh_docs", {})], ctx)
    assert ack["status"] == "done" and "6 new trades" in ack["note"]
    assert db.execute("select count(*) from lots").fetchone()[0] == 4   # no split on file yet: the 20-share sell is short by 7, reported as a problem
    assert db.execute("select count(*) from sales").fetchone()[0] == 2


def test_refresh_docs_refreshes_the_page_and_survives_a_failed_deploy(db):
    seen = []

    def publish(d):
        seen.append(1)
        raise RuntimeError("wrangler exited 1")
    ctx = vmqueue.Context(sync_docs=lambda d: "Synced.", publish=publish)
    [ack] = poll(db, [queue_item("001", "refresh_docs", {})], ctx)
    assert seen and ack["status"] == "done" and "page refresh failed" in ack["note"]


def test_rerun_asks_the_next_tick_to_run_the_job_again(db):
    asked = []
    ctx = vmqueue.Context(rerun=asked.append)
    good, bad = poll(db, [queue_item("001", "rerun", {}), queue_item("002", "rerun", {"job": "rm -rf"})], ctx)
    assert asked == ["daily"]
    assert good["status"] == "done" and bad["status"] == "failed"


def test_build_tax_pack_builds_it_lists_it_on_the_page_and_republishes(tmp_path, db):
    cfg = config.load(tmp_path)
    published = []
    ctx = vmqueue.Context(build_pack=lambda d: ship.build_tax_pack(d, cfg), publish=lambda d: published.append(1) or "Live.")
    [ack] = poll(db, [queue_item("001", "build_tax_pack", {})], ctx)
    assert ack["status"] == "done" and "built" in ack["note"] and ack["note"].endswith("Live.")
    assert published and list((tmp_path / "data" / "tax_pack").glob("*/summary.json"))
    assert site.weekly_view(db, "tax")["fy"]


def test_budget_and_target_payloads_from_the_dashboard_are_understood(db):
    poll(db, [queue_item("001", "budget_set", {"month": "2026-12", "amount": 50000}),
              queue_item("002", "allocation_approve", {"target": {"stocks": 0.6}})], vmqueue.Context())
    assert db.execute("select amount_inr from budgets").fetchone()[0] == 50000
    assert json.loads(db.execute("select allocation from target_allocations").fetchone()[0]) == {"stocks": 0.6}
