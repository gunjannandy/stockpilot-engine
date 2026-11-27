"""`due(state, now)`: a table of (state, clock) -> jobs. Pure; no database."""
from datetime import datetime

import pytest

from stockpilot.jobs import due
from stockpilot.jobs.due import State

FRIDAY = datetime(2026, 11, 20)        # a trading day
SATURDAY = datetime(2026, 11, 21)
SUNDAY_FIRST = datetime(2026, 11, 1)   # 2026-11-01 is a Sunday
SUNDAY_LATER = datetime(2026, 11, 8)


def at(day, hour, minute=0):
    return day.replace(hour=hour, minute=minute)


NSE_AND_INDICES = frozenset({"nse_prices", "indices"})
ALL = frozenset(due.GATHER_SOURCES)


def s(**kw):
    return State(**{"trading_day": True, "ownership_done": True, **kw})


TABLE = [
    # the queue runs every tick, nothing else when nothing is due
    ("quiet morning",              s(), at(FRIDAY, 9), ["queue"]),
    ("15:59 nothing to gather",    s(), at(FRIDAY, 15, 59), ["queue"]),
    ("not a trading day",          s(trading_day=False), at(FRIDAY, 19, 3), ["queue"]),
    ("holiday by the exchange",    s(ingest="holiday"), at(FRIDAY, 19, 3), ["queue"]),
    # gather: from 16:00, each tick, until every source is in (or 23:00)
    ("16:00 gather starts",        s(), at(FRIDAY, 16), ["queue", "gather"]),
    ("gather retries what is missing", s(gathered=NSE_AND_INDICES), at(FRIDAY, 17), ["queue", "gather"]),
    ("everything gathered",        s(gathered=ALL), at(FRIDAY, 17), ["queue"]),
    ("gather stops at 23:00",      s(gathered=NSE_AND_INDICES, decide_done=True), at(FRIDAY, 23, 3), ["queue"]),
    # crunch: 22:00, or earlier from 19:00 once the required sources are in
    ("19:30 required done: crunch", s(gathered=NSE_AND_INDICES), at(FRIDAY, 19, 30), ["queue", "crunch"]),
    ("19:30 NSE missing: gather",  s(gathered=frozenset({"indices", "bse_prices"})), at(FRIDAY, 19, 30), ["queue", "gather"]),
    ("18:30 required done: not yet", s(gathered=NSE_AND_INDICES), at(FRIDAY, 18, 30), ["queue", "gather"]),
    ("22:00 NSE missing: crunch",  s(gathered=frozenset({"indices"})), at(FRIDAY, 22), ["queue", "crunch"]),
    ("22:00 nothing gathered: crunch", s(), at(FRIDAY, 22), ["queue", "crunch"]),
    ("after decide done: no crunch", s(gathered=NSE_AND_INDICES, decide_done=True, decide_runs=1), at(FRIDAY, 22, 5), ["queue", "gather"]),
    ("decide done, all gathered",  s(gathered=ALL, decide_done=True, decide_runs=1), at(FRIDAY, 22, 5), ["queue"]),
    ("one failed decide: retry",   s(gathered=ALL, decide_runs=1), at(FRIDAY, 20), ["queue", "crunch"]),
    ("two decides: no third",      s(gathered=ALL, decide_runs=2), at(FRIDAY, 20), ["queue"]),
    ("late retry after 23:00",     s(gathered=ALL, decide_runs=1), at(FRIDAY, 23, 13), ["queue", "crunch"]),
    ("stale crunch done, NSE still missing", s(gathered=frozenset({"indices"}), stale_crunch=True), at(FRIDAY, 22, 30), ["queue", "gather"]),
    ("stale crunch, then NSE arrives", s(gathered=NSE_AND_INDICES, stale_crunch=True), at(FRIDAY, 22, 30), ["queue", "crunch"]),
    ("crunch crashing: capped",    s(gathered=ALL, crunch_runs=3), at(FRIDAY, 22, 30), ["queue"]),
    ("crunch before gather",       s(gathered=NSE_AND_INDICES), at(FRIDAY, 22), ["queue", "crunch"]),
    # nav once after 23:30
    ("nav before 23:30",           s(decide_done=True, gathered=ALL), at(FRIDAY, 23, 23), ["queue"]),
    ("nav at 23:33",               s(decide_done=True, gathered=ALL), at(FRIDAY, 23, 33), ["queue", "nav"]),
    ("nav done",                   s(decide_done=True, gathered=ALL, nav_done=True), at(FRIDAY, 23, 43), ["queue"]),
    ("nav failed once: retry",     s(decide_done=True, gathered=ALL, nav_runs=1), at(FRIDAY, 23, 43), ["queue", "nav"]),
    ("nav failed twice: stop",     s(decide_done=True, gathered=ALL, nav_runs=2), at(FRIDAY, 23, 53), ["queue"]),
    ("nav on a weekend",           s(trading_day=False), at(SATURDAY, 23, 33), ["queue", "nav"]),
    ("crunch goes before nav",     s(), at(FRIDAY, 22, 53), ["queue", "crunch"]),
    # weekly: Saturday from 10:00
    ("Saturday 09:53",             s(trading_day=False), at(SATURDAY, 9, 53), ["queue"]),
    ("Saturday 10:03",             s(trading_day=False), at(SATURDAY, 10, 3), ["queue", "weekly"]),
    ("weekly done",                s(trading_day=False, weekly_done=True), at(SATURDAY, 14), ["queue"]),
    ("weekly failed twice",        s(trading_day=False, weekly_runs=2), at(SATURDAY, 14), ["queue"]),
    ("weekly resumes next tick",   s(trading_day=False, weekly_runs=1), at(SATURDAY, 10, 13), ["queue", "weekly"]),
    ("Friday has no weekly",       s(), at(FRIDAY, 10, 3), ["queue"]),
    ("nav before weekly",          s(trading_day=False), at(SATURDAY, 23, 33), ["queue", "nav"]),
    # base rates: the first Sunday of the month at 03:00
    ("first Sunday 02:53",         s(trading_day=False), at(SUNDAY_FIRST, 2, 53), ["queue"]),
    ("first Sunday 03:03",         s(trading_day=False), at(SUNDAY_FIRST, 3, 3), ["queue", "base_rates"]),
    ("first Sunday, done",         s(trading_day=False, base_rates_done=True), at(SUNDAY_FIRST, 9), ["queue"]),
    ("second Sunday",              s(trading_day=False), at(SUNDAY_LATER, 3, 3), ["queue"]),
    # a rerun asked for on the dashboard or by the doctor
    ("rerun daily at noon",        s(gathered=ALL, decide_done=True, rerun=frozenset({"daily"})), at(FRIDAY, 12), ["queue", "daily"]),
    ("rerun nav",                  s(rerun=frozenset({"nav"})), at(FRIDAY, 12), ["queue", "nav"]),
    ("rerun kite",                 s(rerun=frozenset({"kite"})), at(FRIDAY, 12), ["queue", "kite"]),
    ("rerun weekly on a Monday",   s(rerun=frozenset({"weekly"})), at(FRIDAY, 12), ["queue", "weekly"]),
    ("one job at a time",          s(rerun=frozenset({"nav", "weekly"})), at(FRIDAY, 12), ["queue", "nav"]),
]


@pytest.mark.parametrize("state,now,expected", [t[1:] for t in TABLE], ids=[t[0] for t in TABLE])
def test_what_is_due(state, now, expected):
    assert due.due(state, now) == expected


def test_the_queue_is_always_first_and_at_most_one_job_follows():
    for _, state, now, expected in TABLE:
        assert expected[0] == "queue" and len(expected) <= 2


def test_gave_up_is_true_only_from_23_00_with_no_nse_prices_and_no_holiday():
    assert due.gave_up(s(), at(FRIDAY, 23, 3))                                  # never even reached NSE
    assert due.gave_up(s(gathered=frozenset({"indices"})), at(FRIDAY, 23, 3))
    assert not due.gave_up(s(), at(FRIDAY, 22, 53))
    assert not due.gave_up(s(gathered=NSE_AND_INDICES), at(FRIDAY, 23, 3))
    assert not due.gave_up(s(ingest="holiday"), at(FRIDAY, 23, 3))
    assert not due.gave_up(s(trading_day=False), at(FRIDAY, 23, 3))


def test_missing_sources_from_23_00_are_listed_in_gather_order():
    got = due.missing_sources(s(gathered=NSE_AND_INDICES - {"indices"} | {"bse_prices"}), at(FRIDAY, 23, 3))
    assert got[0] == "indices" and "nse_prices" not in got and "bse_prices" not in got
    assert due.missing_sources(s(gathered=ALL), at(FRIDAY, 23, 3)) == []
    assert due.missing_sources(s(), at(FRIDAY, 22, 53)) == []                   # not yet 23:00
    assert due.missing_sources(s(trading_day=False), at(FRIDAY, 23, 3)) == []


# ---- reading the state from the runs table and the calendar --------------------------------------------

def _runs(db, *rows):
    for job, status, at_ in rows:
        db.execute("insert into runs (job, started_at, status) values (?, ?, ?)", [job, at_, status])


def test_read_state_counts_only_today_and_knows_the_calendar(tmp_path):
    from stockpilot import store
    db = store.open(tmp_path / "sp.duckdb")
    _runs(db, ("daily_ingest", "ok", datetime(2026, 11, 19, 19, 5)),               # yesterday: ignored
            ("daily_ingest", "waiting", datetime(2026, 11, 20, 19, 5)),
            ("daily_ingest", "ok", datetime(2026, 11, 20, 19, 25)),
            ("daily_decide", "failed", datetime(2026, 11, 20, 19, 40)),
            ("nav", "failed", datetime(2026, 11, 20, 23, 35)),
            ("weekly", "failed", datetime(2026, 11, 20, 10, 5)))
    state = due.read_state(db, datetime(2026, 11, 20, 19, 50), tmp_path)
    assert state == State(trading_day=True, ingest="ok", decide_done=False, decide_runs=1, nav_done=False, nav_runs=1,
                          weekly_done=False, weekly_runs=1, base_rates_done=False, rerun=frozenset())
    assert due.due(state, datetime(2026, 11, 20, 19, 50)) == ["queue", "gather"]      # nothing marked gathered yet
    assert not due.read_state(db, datetime(2026, 11, 21, 12), tmp_path).trading_day            # Saturday


def test_a_failed_rerun_after_a_good_ingest_still_counts_the_prices_as_in(tmp_path):
    from stockpilot import store
    db = store.open(tmp_path / "sp.duckdb")
    _runs(db, ("daily_ingest", "ok", datetime(2026, 11, 20, 19, 5)), ("daily_ingest", "failed", datetime(2026, 11, 20, 21, 5)))
    assert due.read_state(db, datetime(2026, 11, 20, 21, 30), tmp_path).ingest == "ok"


def test_rerun_files_are_read_and_taken(tmp_path):
    due.ask_rerun(tmp_path, "nav")
    (tmp_path / "data" / "rerun" / "rm -rf").write_text("x")          # anything else in the folder is ignored
    assert due.pending_reruns(tmp_path) == {"nav"}
    due.take_rerun(tmp_path, "nav")
    assert due.pending_reruns(tmp_path) == frozenset()


def test_read_state_reads_today_markers_and_stale_crunches(tmp_path):
    from stockpilot import store
    db = store.open(tmp_path / "sp.duckdb")
    db.execute("insert into fetch_log values ('gathered', '2026-11-19:nse_prices'), ('gathered', '2026-11-20:indices'), "
               "('gathered', '2026-11-20:bse_prices')")
    _runs(db, ("crunch", "partial", datetime(2026, 11, 20, 22, 5)), ("crunch", "failed", datetime(2026, 11, 20, 22, 1)))
    db.execute("update runs set notes = '{\"stale\": true}' where job = 'crunch' and status = 'partial'")
    state = due.read_state(db, datetime(2026, 11, 20, 22, 30), tmp_path)
    assert state.gathered == {"indices", "bse_prices"}                           # yesterday's marker is not today's
    assert state.stale_crunch and state.crunch_runs == 2
    assert due.due(state, datetime(2026, 11, 20, 22, 30)) == ["queue", "gather"]
