import json
from datetime import date

import pytest

from fake_worker import KEY, FakeWorker
from fakes import queue_item
from stockpilot import store, vmqueue, watchlist
from stockpilot.sources import kite
from stockpilot.book import budget


def run(db, queue):
    w = FakeWorker(queue=queue)
    try:
        return vmqueue.poll(db, kite.Worker(w.url, KEY)), w.acks
    finally:
        w.close()


def test_watchlist_add_and_remove_apply_and_ack_done(db):
    summary, acks = run(db, [queue_item("001", "watchlist_add", {"symbol": "SBIN", "exchange": "NSE"}),
                             queue_item("002", "watchlist_add", {"symbol": "TCS", "exchange": "NSE"}),
                             queue_item("003", "watchlist_remove", {"symbol": "TCS", "exchange": "NSE"})])
    assert watchlist.active(db) == [("SBIN", "NSE")]
    assert [(a["id"], a["status"]) for a in acks] == [("001", "done"), ("002", "done"), ("003", "done")]
    assert summary == {"done": 3, "failed": 0}
    assert db.execute("select added_by from watchlist where symbol = 'SBIN'").fetchone() == ("father",)


def test_budget_set_stores_the_month_and_replaces_an_earlier_value(db):
    run(db, [queue_item("001", "budget_set", {"month": "2026-12", "amount_inr": 150000}),
             queue_item("002", "budget_set", {"month": "2026-12", "amount_inr": 120000}, by="owner")])
    assert db.execute("select month, amount_inr, set_by from budgets").fetchall() == [("2026-12", 120000.0, "owner")]
    assert budget.for_month(db, date(2026, 12, 9), 100000) == 120000
    assert budget.for_month(db, date(2027, 1, 2), 100000) == 100000   # no carry-over


def test_bad_payload_is_acked_failed_with_a_plain_note_and_the_rest_continue(db):
    _, acks = run(db, [queue_item("001", "budget_set", {"month": "next", "amount_inr": -5}),
                       queue_item("002", "watchlist_add", {"symbol": "SBIN", "exchange": "NSE"}),
                       queue_item("003", "watchlist_add", {"symbol": "bad symbol!", "exchange": "NSE"})])
    assert [a["status"] for a in acks] == ["failed", "done", "failed"]
    assert acks[0]["note"] and acks[2]["note"]
    assert watchlist.active(db) == [("SBIN", "NSE")]


def test_a_kind_with_no_handler_yet_fails_clearly(db):
    _, acks = run(db, [queue_item("001", "build_tax_pack", {})])
    assert acks[0]["status"] == "failed" and "build_tax_pack" in acks[0]["note"]


def test_allocation_approve_records_the_target(db):
    run(db, [queue_item("001", "allocation_approve", {"equity": 0.7, "debt": 0.3})])
    assert db.execute("select approved_by, allocation from target_allocations").fetchone() == (
        "father", json.dumps({"equity": 0.7, "debt": 0.3}))


def test_polling_again_does_not_reapply_and_resumes_after_the_last_id(db):
    q = [queue_item("001", "watchlist_add", {"symbol": "SBIN", "exchange": "NSE"})]
    run(db, q)
    _, acks = run(db, q + [queue_item("002", "watchlist_add", {"symbol": "TCS", "exchange": "NSE"})])
    assert [a["id"] for a in acks] == ["002"]


def test_an_applied_request_whose_ack_was_lost_is_acked_on_the_next_poll(db):
    db.execute("insert into requests (kind, payload, status, remote_id, acked, note) "
               "values ('watchlist_add', '{}', 'done', '001', false, 'Added.')")
    _, acks = run(db, [])
    assert [(a["id"], a["status"], a["note"]) for a in acks] == [("001", "done", "Added.")]
    assert db.execute("select acked from requests").fetchone() == (True,)


def test_a_request_left_received_by_a_dead_machine_is_failed_and_acked(db):
    db.execute("insert into requests (kind, payload, status, remote_id, acked) values ('refresh_docs', '{}', 'received', '004', false)")
    _, acks = run(db, [])
    assert [(a["id"], a["status"], a["note"]) for a in acks] == [
        ("004", "failed", "The machine stopped while doing this; press the button again.")]
    assert db.execute("select status, note, acked, applied_at is not null from requests").fetchone() == (
        "failed", "The machine stopped while doing this; press the button again.", True, True)


def test_a_received_row_is_failed_only_at_the_start_of_the_next_poll_not_for_the_current_one(db):
    _, acks = run(db, [queue_item("001", "watchlist_add", {"symbol": "SBIN", "exchange": "NSE"})])
    assert [(a["id"], a["status"]) for a in acks] == [("001", "done")]


# Lane W: long_term_mark and ask_analyst
def test_long_term_mark_on_and_off(db):
    run(db, [queue_item("001", "long_term_mark", {"symbol": "JIOFIN", "on": True}, by="father")])
    assert db.execute("select symbol, marked_by from long_term_marks").fetchall() == [("JIOFIN", "father")]
    run(db, [queue_item("002", "long_term_mark", {"symbol": "JIOFIN", "on": True})])      # again: still one row
    assert db.execute("select count(*) from long_term_marks").fetchone()[0] == 1
    _, acks = run(db, [queue_item("003", "long_term_mark", {"symbol": "JIOFIN", "on": False})])
    assert db.execute("select count(*) from long_term_marks").fetchone()[0] == 0
    assert acks[0]["status"] == "done"


def test_long_term_mark_survives_trade_tag_rebuild(db):
    run(db, [queue_item("001", "long_term_mark", {"symbol": "TCS", "on": True})])
    db.execute("delete from trade_tags")           # smallcase.rebuild does this on every sync
    assert db.execute("select count(*) from long_term_marks").fetchone()[0] == 1


def test_long_term_mark_rejects_bad_input(db):
    _, acks = run(db, [queue_item("001", "long_term_mark", {"symbol": "bad symbol!", "on": True}),
                       queue_item("002", "long_term_mark", {"symbol": "TCS", "on": "maybe"})])
    assert [a["status"] for a in acks] == ["failed", "failed"]
    assert db.execute("select count(*) from long_term_marks").fetchone()[0] == 0


def test_ask_analyst_records_one_pending_ask(db):
    _, acks = run(db, [queue_item("001", "ask_analyst", {"symbol": "sbin"}, by="father")])
    assert acks[0]["status"] == "done"
    assert db.execute("select symbol, asked_by, status from analyst_asks").fetchall() == [("SBIN", "father", "pending")]


def test_ask_analyst_same_stock_twice_is_one_ask(db):
    run(db, [queue_item("001", "ask_analyst", {"symbol": "SBIN"}), queue_item("002", "ask_analyst", {"symbol": "SBIN"})])
    assert db.execute("select count(*) from analyst_asks where status = 'pending'").fetchone()[0] == 1


def test_ask_analyst_cap_of_five_a_day(db):
    items = [queue_item(f"{i:03d}", "ask_analyst", {"symbol": s}) for i, s in enumerate(["A", "B", "C", "D", "E", "F"], 1)]
    _, acks = run(db, items)
    assert [a["status"] for a in acks] == ["done"] * 5 + ["failed"]
    assert "5" in acks[5]["note"]
    assert db.execute("select count(*) from analyst_asks").fetchone()[0] == 5


def test_ask_analyst_needs_a_symbol(db):
    _, acks = run(db, [queue_item("001", "ask_analyst", {})])
    assert acks[0]["status"] == "failed"


def test_new_tables_are_backed_up():
    from stockpilot import backup
    for t in ("long_term_marks", "analyst_asks"):
        assert t in backup.STATE_TABLES and t in backup.ADDED_LATER


def test_a_fund_is_watched_by_its_isin_on_the_amfi_list_and_a_stock_cannot_use_amfi(db):
    _, acks = run(db, [queue_item("001", "watchlist_add", {"symbol": "INF879O01027", "exchange": "AMFI"}),
                       queue_item("002", "watchlist_add", {"symbol": "SBIN", "exchange": "AMFI"})])
    assert [a["status"] for a in acks] == ["done", "failed"]
    assert watchlist.active(db) == [("INF879O01027", "AMFI")]
