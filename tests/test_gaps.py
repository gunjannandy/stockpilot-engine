"""Lane C: the gaps ledger and an honest Health headline."""
from datetime import date, datetime

import pytest

from stockpilot import gaps, site, store
from stockpilot.sources import navhistory  # noqa: F401


@pytest.fixture
def db(tmp_path):
    return store.open(tmp_path / "sp.duckdb")


def test_record_is_idempotent_and_counts_by_reason(db):
    gaps.record(db, "price_history", "IGARASHI", "not_collected", "history exists for 220 of 1617 stocks")
    gaps.record(db, "price_history", "IGARASHI", "not_collected", "still missing")
    gaps.record(db, "fidelity", "ServiceNow", "parse_failed", "9 documents, 0 events")
    gaps.record(db, "ownership", "TCS", "waiting_on_owner", "needs login")
    rows = gaps.open_gaps(db)
    assert len(rows) == 3
    assert next(r for r in rows if r["subject"] == "IGARASHI")["detail"] == "still missing"
    assert gaps.summary(db) == {"not_collected": 1, "parse_failed": 1, "waiting_on_owner": 1}


def test_unknown_reason_is_refused(db):
    with pytest.raises(ValueError):
        gaps.record(db, "x", "y", "because", "")


def test_resolve_closes_a_gap_and_a_new_record_reopens_it(db):
    gaps.record(db, "price_history", "A", "source_down", "")
    gaps.resolve(db, "price_history", "A")
    assert gaps.open_gaps(db) == []
    gaps.record(db, "price_history", "A", "source_down", "")
    assert len(gaps.open_gaps(db)) == 1


def test_weekly_note_lists_gaps_in_plain_words(db):
    gaps.record(db, "price_history", "IGARASHI", "not_collected", "")
    gaps.record(db, "price_history", "ABC", "quota", "")
    note = gaps.weekly_note(db)
    assert "2 gaps" in note and "IGARASHI" in note
    assert gaps.weekly_note(db).startswith("2 gaps")


def test_weekly_note_is_empty_when_nothing_is_open(db):
    assert gaps.weekly_note(db) == ""


def _health(db):
    return site._health(db, date(2026, 11, 20), datetime(2026, 11, 20, 19, 30), date(2026, 11, 20))


def test_health_headline_is_working_only_when_nothing_is_open(db):
    h = _health(db)
    assert h["headline"] == "Everything is working." and h["gaps"] == []


def test_health_headline_counts_open_problems_and_gaps(db):
    for i in range(3):
        db.execute("insert into problems (job, severity, message, key) values ('x', 'warning', ?, ?)", [f"p{i}", f"k{i}"])
    db.execute("insert into problems (job, severity, message, key, resolution) values ('x','warning','old','old','fixed')")
    gaps.record(db, "price_history", "IGARASHI", "not_collected", "no history")
    gaps.record(db, "price_history", "ABC", "not_collected", "no history")
    gaps.record(db, "fidelity", "ServiceNow", "parse_failed", "0 events")
    h = _health(db)
    assert h["headline"] == "5 things need you." and "working" not in h["headline"]
    assert h["open_problems"] == 3
    assert {g["subject"] for g in h["gaps"]} == {"IGARASHI", "ABC", "ServiceNow"}
    assert {g["subject"]: g["reason"] for g in h["gaps"]}["ABC"] == "Not collected yet"


def test_one_open_problem_is_singular(db):
    db.execute("insert into problems (job, severity, message, key) values ('x', 'warning', 'p', 'k')")
    assert _health(db)["headline"] == "One thing needs you."
