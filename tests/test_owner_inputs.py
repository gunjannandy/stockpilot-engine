"""R5: Not now (set, undo, expiry), acted-on detection, budget left, settings.json, and the kinds file."""
import json
from datetime import date
from pathlib import Path

import pytest

from fake_worker import KEY, FakeWorker
from stockpilot import forecast, store, vmqueue, watchlist
from stockpilot.sources import kite
from stockpilot.book import acted, budget, not_now

DAY = date(2026, 11, 2)   # a Monday


def item(id_, kind, payload, by="father"):
    return {"id": id_, "kind": kind, "payload": payload, "by": by, "at": "2026-11-02T08:00:00Z"}


def run(db, queue):
    w = FakeWorker(queue=queue)
    try:
        return vmqueue.poll(db, kite.Worker(w.url, KEY)), w.acks
    finally:
        w.close()


# ---- not_now -------------------------------------------------------------------------------------------

def test_not_now_for_a_week_a_month_and_for_good(db):
    not_now.set(db, "SBIN", "buy", "week", "father", DAY)
    not_now.set(db, "TCS", "sell", "month", "father", DAY)
    not_now.set(db, "INFY", "any", "good", "owner", DAY)
    until = dict(db.execute("select symbol, until from not_now").fetchall())
    assert until == {"SBIN": date(2026, 11, 9), "TCS": date(2026, 12, 2), "INFY": None}
    assert not_now.active(db, DAY) == {("SBIN", "buy"), ("TCS", "sell"), ("INFY", "any")}


def test_not_now_expires_after_its_last_day(db):
    not_now.set(db, "SBIN", "buy", "week", "father", DAY)
    not_now.set(db, "INFY", "any", "good", "father", DAY)
    assert ("SBIN", "buy") in not_now.active(db, date(2026, 11, 9))
    assert not_now.active(db, date(2026, 11, 10)) == {("INFY", "any")}
    assert not_now.active(db, date(2030, 1, 1)) == {("INFY", "any")}


def test_undo_brings_the_stock_back_and_cannot_be_repeated(db):
    nid = not_now.set(db, "SBIN", "buy", "month", "father", DAY)
    not_now.undo(db, nid)
    assert not_now.active(db, DAY) == set()
    with pytest.raises(ValueError):
        not_now.undo(db, nid)
    with pytest.raises(ValueError):
        not_now.undo(db, 999)


def test_setting_the_same_thing_again_extends_it_without_a_second_row(db):
    first = not_now.set(db, "SBIN", "buy", "week", "father", DAY)
    second = not_now.set(db, "SBIN", "buy", "month", "father", DAY)
    assert first == second
    assert db.execute("select count(*) from not_now").fetchone() == (1,)
    assert db.execute("select until from not_now").fetchone() == (date(2026, 12, 2),)


@pytest.mark.parametrize("args", [("SBIN", "hold", "week"), ("SBIN", "buy", "year"), ("sb in", "buy", "week"), ("", "buy", "week")])
def test_not_now_rejects_bad_input(db, args):
    with pytest.raises(ValueError):
        not_now.set(db, *args, "father", DAY)


# ---- the queue kinds -----------------------------------------------------------------------------------

def test_queue_applies_not_now_and_undo_and_acks_each(db):
    _, acks = run(db, [item("001", "not_now", {"symbol": "sbin", "scope": "buy", "for": "week"})])
    assert [(a["id"], a["status"]) for a in acks] == [("001", "done")]
    nid = db.execute("select id from not_now").fetchone()[0]
    assert db.execute("select set_by from not_now").fetchone() == ("father",)
    assert ("SBIN", "buy") in not_now.active(db, date.today())
    _, acks = run(db, [item("002", "not_now_undo", {"id": nid})])
    assert acks[-1]["status"] == "done" and not_now.active(db, date.today()) == set()


def test_queue_not_now_fails_with_a_plain_note_on_bad_input(db):
    _, acks = run(db, [item("001", "not_now", {"symbol": "SBIN", "scope": "buy", "for": "forever"}),
                       item("002", "not_now_undo", {"id": 12345})])
    assert [a["status"] for a in acks] == ["failed", "failed"]
    assert all(a["note"] for a in acks)


def test_kinds_file_matches_the_vm_handlers():
    kinds = json.loads((Path(vmqueue.__file__).parents[2] / "schemas" / "queue-kinds.json").read_text())
    assert set(kinds["kinds"]) == set(vmqueue.HANDLERS)
    assert kinds["kinds"]["not_now"] == ["symbol", "scope", "for"]
    assert kinds["kinds"]["not_now_undo"] == ["id"]
    assert kinds["kinds"]["snooze"] == kinds["kinds"]["dismiss"] == ["symbol", "scope"]


# ---- snooze and dismiss (R5b) -------------------------------------------------------------------------

def test_snooze_hides_for_30_days_and_dismiss_until_undone(db):
    a = not_now.set(db, "SBIN", "buy", "snooze", "father", DAY)
    b = not_now.set(db, "TCS", "any", "dismiss", "owner", DAY)
    assert db.execute("select how, until from not_now where id = ?", [a]).fetchone() == ("snooze", date(2026, 12, 2))
    assert db.execute("select how, until from not_now where id = ?", [b]).fetchone() == ("dismiss", None)
    assert not_now.active(db, date(2026, 12, 2)) == {("SBIN", "buy"), ("TCS", "any")}
    assert not_now.active(db, date(2026, 12, 3)) == {("TCS", "any")}


def test_old_not_now_words_are_an_alias(db):
    ids = [not_now.set(db, s, "buy", f, "father", DAY) for s, f in (("A", "week"), ("B", "month"), ("C", "good"))]
    rows = db.execute("select symbol, how, until from not_now order by id").fetchall()
    assert rows == [("A", "snooze", date(2026, 11, 9)), ("B", "snooze", date(2026, 12, 2)), ("C", "dismiss", None)]


def test_a_snooze_never_weakens_a_dismissal(db):
    a = not_now.set(db, "SBIN", "buy", "dismiss", "father", DAY)
    assert not_now.set(db, "SBIN", "buy", "snooze", "father", DAY) == a
    assert db.execute("select how, until from not_now").fetchone() == ("dismiss", None)


def test_undo_works_for_both_and_dismissed_lists_undone_ones_too(db):
    a = not_now.set(db, "SBIN", "buy", "dismiss", "father", DAY)
    not_now.set(db, "TCS", "buy", "snooze", "father", DAY)
    not_now.set(db, "INFY", "sell", "dismiss", "owner", DAY)
    not_now.undo(db, a)
    assert not_now.active(db, DAY) == {("TCS", "buy"), ("INFY", "sell")}
    got = not_now.dismissed(db)
    assert [(d["symbol"], d["scope"], d["undone_at"] is not None) for d in got] == [("SBIN", "buy", True), ("INFY", "sell", False)]
    assert got[0]["id"] == a and got[1]["set_by"] == "owner"


def test_queue_snooze_dismiss_and_alias(db):
    _, acks = run(db, [item("1", "snooze", {"symbol": "sbin", "scope": "buy"}),
                       item("2", "dismiss", {"symbol": "tcs", "scope": "any"}),
                       item("3", "not_now", {"symbol": "infy", "scope": "sell", "for": "good"}),
                       item("4", "snooze", {"symbol": "x y", "scope": "buy"}),
                       item("5", "dismiss", {"symbol": "TCS", "scope": "maybe"})])
    assert [a["status"] for a in acks] == ["done", "done", "done", "failed", "failed"]
    assert dict(db.execute("select symbol, how from not_now").fetchall()) == {"SBIN": "snooze", "TCS": "dismiss", "INFY": "dismiss"}
    nid = db.execute("select id from not_now where symbol = 'TCS'").fetchone()[0]
    _, acks = run(db, [item("6", "not_now_undo", {"id": nid})])
    assert acks[-1]["status"] == "done"
    assert ("TCS", "any") not in not_now.active(db, date.today())


def test_settings_lists_how_and_industry_and_the_forecaster_is_untouched(db):
    db.execute("insert into stocks (symbol, industry) values ('SBIN', 'Banks')")
    not_now.set(db, "SBIN", "buy", "dismiss", "father", DAY)
    items = not_now.settings_payload(db, DAY, 1000)["not_now"]
    assert items[0]["how"] == "dismiss" and items[0]["industry"] == "Banks" and items[0]["until"] is None


# ---- acted on ------------------------------------------------------------------------------------------

def call(db, symbol, action, made_on=DAY, size=20000.0, section=None):
    db.execute("insert into calls (made_on, symbol, kind, action, size_inr, section) values (?, ?, 'stock', ?, ?, ?)",
               [made_on, symbol, action, size, section or action])


def trade(db, symbol, side, day, key=None):
    db.execute("insert into trades (trade_key, source, kind, symbol, side, trade_date, quantity, price) "
               "values (?, 'contract_note', 'stock', ?, ?, ?, 10, 100)", [key or f"{symbol}{side}{day}", symbol, side, day])


def acted_on(db, symbol):
    return db.execute("select acted_on from calls where symbol = ?", [symbol]).fetchone()[0]


def test_a_buy_three_trading_days_after_a_buy_call_marks_it_acted_on(db):
    call(db, "SBIN", "buy")
    trade(db, "SBIN", "buy", date(2026, 11, 5))     # Thursday: 3 trading days
    assert acted.mark(db) == 1
    assert acted_on(db, "SBIN") == date(2026, 11, 5)


def test_a_buy_six_trading_days_after_does_not(db):
    call(db, "SBIN", "buy")
    trade(db, "SBIN", "buy", date(2026, 11, 10))    # Tuesday: 6 trading days
    assert acted.mark(db) == 0 and acted_on(db, "SBIN") is None


def test_the_window_skips_weekends_and_holidays(db):
    db.execute("insert into holidays values (?, 'x')", [date(2026, 11, 4)])
    call(db, "SBIN", "buy")
    trade(db, "SBIN", "buy", date(2026, 11, 10))    # Nov 3, 5, 6, 9, 10: five trading days
    assert acted.mark(db) == 1


def test_a_trade_before_the_call_or_of_the_wrong_side_does_not_count(db):
    call(db, "SBIN", "buy")
    call(db, "TCS", "sell")
    call(db, "INFY", "buy")
    trade(db, "SBIN", "buy", date(2026, 10, 30))
    trade(db, "TCS", "buy", date(2026, 11, 3))
    trade(db, "INFY", "sell", date(2026, 11, 3))
    assert acted.mark(db) == 0


def test_a_sell_after_a_sell_or_trim_call_marks_it(db):
    call(db, "TCS", "sell")
    call(db, "INFY", "trim")
    trade(db, "TCS", "sell", date(2026, 11, 3))
    trade(db, "INFY", "sell", date(2026, 11, 4))
    assert acted.mark(db) == 2


def test_marking_is_repeatable_and_keeps_the_first_date(db):
    call(db, "SBIN", "buy")
    trade(db, "SBIN", "buy", date(2026, 11, 3))
    acted.mark(db)
    trade(db, "SBIN", "buy", date(2026, 11, 4))
    assert acted.mark(db) == 0 and acted_on(db, "SBIN") == date(2026, 11, 3)


def test_a_kite_trade_from_the_last_sync_counts(db):
    call(db, "SBIN", "buy")
    trades = [{"tradingsymbol": "SBIN", "transaction_type": "BUY", "fill_timestamp": "2026-11-03 10:15:00"}]
    db.execute("insert into kite_syncs values (?, ?, null, null, null)", [date(2026, 11, 3), json.dumps(trades)])
    assert acted.mark(db) == 1 and acted_on(db, "SBIN") == date(2026, 11, 3)


def test_budget_left_falls_by_a_detected_buy_only(db):
    budget.set_month(db, "2026-11", 100000, "father")
    call(db, "SBIN", "buy", size=30000)
    call(db, "TCS", "buy", size=25000)
    assert forecast.budget_left(db, DAY, 100000) == 100000
    trade(db, "SBIN", "buy", date(2026, 11, 3))
    acted.mark(db)
    assert forecast.budget_left(db, DAY, 100000) == 70000


# ---- settings.json -------------------------------------------------------------------------------------

def test_settings_payload(db):
    budget.set_month(db, "2026-11", 100000, "father")
    watchlist.add(db, "SBIN", "NSE", "father")
    nid = not_now.set(db, "TCS", "sell", "week", "father", DAY)
    not_now.set(db, "INFY", "buy", "week", "father", DAY)
    not_now.undo(db, db.execute("select id from not_now where symbol = 'INFY'").fetchone()[0])
    call(db, "SBIN", "buy", size=30000)
    trade(db, "SBIN", "buy", date(2026, 11, 3))
    acted.mark(db)
    body = not_now.settings_payload(db, DAY, 100000)
    assert body["as_of"] == "2026-11-02"
    assert body["not_now"] == [{"id": nid, "symbol": "TCS", "scope": "sell", "until": "2026-11-09", "set_by": "father",
                                "how": "snooze", "industry": None}]
    assert body["budget"] == {"month": "2026-11", "total": 100000, "left": 70000}
    assert body["watchlist_count"] == 1


def test_a_sync_marks_acted_calls_and_says_so(db):
    from stockpilot.jobs import docs as pipeline
    call(db, "SBIN", "buy")
    trade(db, "SBIN", "buy", date(2026, 11, 3))
    assert pipeline.mark_acted(db) == " 1 call marked acted on."
    assert pipeline.mark_acted(db) == ""
