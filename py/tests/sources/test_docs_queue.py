"""Documents that Gmail's daily limit kept us from downloading are a queue: oldest first, never asked for again
until the limit resets, and resumed by the next day's sync with no owner step."""
from datetime import datetime, timezone

import pytest

from stockpilot import store
from stockpilot.jobs import docs
from stockpilot.sources import google
from stockpilot.trades import feed

QUOTA = google.BridgeError("bridge op att: Service invoked too many times for one day: gmail.")


def utc(d, h=12):
    return datetime(2026, 11, d, h, tzinfo=timezone.utc)


def mail(ident, day, subject="Coin allotment report"):
    return {"source": "gmail", "id": ident, "subject": subject, "date": f"2026-0{day}-01T10:00:00Z",
            "attachments": []}


class Inner(google.Bridge):
    def __init__(self, listing, fail_after=None):
        self.listing, self.calls, self.fail_after = listing, [], fail_after

    def list(self, since=None):
        self.calls.append(("list", since))
        return self.listing

    def body(self, msg_id):
        self.calls.append(("body", msg_id))
        if self.fail_after is not None and len([c for c in self.calls if c[0] == "body"]) > self.fail_after:
            raise QUOTA
        return "no allotment lines here"


def test_after_a_quota_hit_no_later_run_asks_gmail_until_the_limit_resets(tmp_path):
    inner = Inner([mail("m1", 1)], fail_after=0)
    cache = google.Cache(inner, tmp_path, now=lambda: utc(24, 12))
    with pytest.raises(google.Deferred):
        cache.body("m1")
    inner.calls.clear()
    same_day = google.Cache(inner, tmp_path, now=lambda: utc(24, 20))        # a later run, same day
    with pytest.raises(google.Deferred):
        same_day.body("m1")
    same_day.list(since="2026")
    assert inner.calls == []                                                 # the bridge was not touched at all
    inner.fail_after = None                                                  # the limit is lifted
    after_reset = google.Cache(inner, tmp_path, now=lambda: utc(25, 9))      # next day, past the reset
    after_reset.body("m1")
    assert ("body", "m1") in inner.calls


def test_the_oldest_waiting_document_is_read_first(tmp_path):
    inner = Inner([mail("new", 9), mail("old", 2), mail("mid", 5)])
    cache = google.Cache(inner, tmp_path, now=lambda: utc(24))
    out = feed.fetch(cache, "PAN", None, limit=2)
    assert [r["id"] for r in out.handled] == ["old", "mid"] and out.more


def test_the_quota_running_out_keeps_the_oldest_handled_and_defers_the_rest_in_order(tmp_path):
    inner = Inner([mail("c", 9), mail("a", 2), mail("b", 5)], fail_after=1)
    out = feed.fetch(google.Cache(inner, tmp_path, now=lambda: utc(24)), "PAN", None)
    assert [r["id"] for r in out.handled] == ["a"]
    assert out.deferred == ["b", "c"]


def test_the_next_days_sync_resumes_the_queue_and_does_not_relist_the_whole_history(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    inner = Inner([mail("a", 2), mail("b", 5), mail("c", 9)], fail_after=1)
    cache = google.Cache(inner, tmp_path / "docs", now=lambda: utc(24))
    docs.sync_batch(db, cache, "PAN", now=lambda: utc(24))
    assert db.execute("select id from documents order by id").fetchall() == [("a",)]
    inner.fail_after, inner.calls = None, []
    cache2 = google.Cache(inner, tmp_path / "docs", now=lambda: utc(25, 9))
    docs.sync_batch(db, cache2, "PAN", now=lambda: utc(25, 9))
    assert db.execute("select id from documents order by id").fetchall() == [("a",), ("b",), ("c",)]
    since = [c[1] for c in inner.calls if c[0] == "list"]
    assert since and since[0] >= "2026-11-23"                  # a day's window, not the whole history again
