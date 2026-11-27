"""Splits and bonuses that NSE keeps outside its main-board feed: ETF/fund units (index=mf) and SME stocks
(index=sme). Real rows, trimmed."""
import json
from datetime import date
from pathlib import Path

import pytest

from stockpilot import store
from stockpilot.trades import corporate_actions_feeds as feeds

ROWS = json.loads((Path(__file__).parents[1] / "fixtures" / "nse_corporate_actions_other_feeds.json").read_text())


def fetch_json(path):
    for index in ("mf", "sme"):
        if f"index={index}&" in path:
            return ROWS[index]
    return []       # the main-board feed answers nothing in this test


def kinds(db):
    return {(s, str(d), k, n) for s, d, k, n in db.execute(
        "select symbol, ex_date, kind, numerator from corporate_actions").fetchall()}


def test_ingest_stores_fund_unit_splits_and_sme_bonuses(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    feeds.ingest(db, date(2026, 3, 1), fetch_json)
    got = kinds(db)
    assert ("CONS", "2026-02-27", "split", 10.0) in got
    assert ("IVZINGOLD", "2026-04-30", "split", 100.0) in got
    assert ("DIGIKORE", "2025-10-24", "bonus", 1.0) in got
    assert ("FOCE", "2026-03-02", "bonus", 7.0) in got
    assert ("PSRAJ", "2026-07-24", "split", 5.0) in got
    assert not any(s == "SDL26BEES" for s, *_ in got)          # a redemption is not a split


def test_the_request_uses_each_feeds_own_index(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    asked = []
    feeds.ingest(db, date(2026, 3, 1), lambda p: asked.append(p) or [])
    assert [("index=mf&" in p, "index=sme&" in p) for p in asked] == [(True, False), (False, True)]


def test_backfill_is_resumable_per_feed(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    calls = []

    def fj(path):
        calls.append(path)
        return fetch_json(path)
    feeds.backfill(db, fj, date(2026, 1, 1), date(2026, 3, 15))
    first = len(calls)
    assert first == 2 * 3                                       # three months for each feed
    feeds.backfill(db, fj, date(2026, 1, 1), date(2026, 3, 15))
    assert len(calls) - first == 2                              # only the month still running is asked again
    assert ("CONS", "2026-02-27", "split", 10.0) in kinds(db)


def test_one_feed_failing_does_not_stop_the_other(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")

    def fj(path):
        if "index=mf&" in path:
            raise OSError("blocked")
        return fetch_json(path)
    with pytest.raises(RuntimeError, match="mf"):          # the failure is reported, after the other feed is stored
        feeds.ingest(db, date(2026, 3, 1), fj)
    assert ("FOCE", "2026-03-02", "bonus", 7.0) in kinds(db)
