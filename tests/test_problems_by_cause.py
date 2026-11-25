"""Problems by cause: one Health-tab row per cause, not per document; the bridge stops at Gmail's daily limit."""
import json

from pdfs import make_pdf
from stockpilot import store
from stockpilot.sources import google
from stockpilot.jobs import docs
from stockpilot.trades import feed
from test_trades_documents import NOTE
from test_trades_feed import PAN, FakeBridge, msg

QUOTA = "bridge op att: Service invoked too many times for one day: gmail."


class QuotaBridge(google.Bridge):
    """A bridge whose Gmail calls all fail with the daily limit; counts what reaches it."""

    def __init__(self, listing, error=QUOTA):
        self.listing, self.error, self.calls = listing, error, []

    def list(self, since=None):
        return self.listing

    def att(self, msg_id, index):
        self.calls.append(msg_id)
        raise google.BridgeError(self.error)

    def body(self, msg_id):
        self.calls.append(msg_id)
        raise google.BridgeError(self.error)


def mails(n):
    return [msg(f"m{i}", "Zerodha <a@zerodha.net>", "Contract note", 1) for i in range(n)]


def problems(db):
    return db.execute("select key, message, count from problems where job = 'trades' order by id").fetchall()


def test_230_failures_with_one_cause_are_one_problem(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    docs.sync_docs(db, QuotaBridge(mails(230)), PAN)
    [(key, message, _)] = problems(db)
    assert key.startswith("docs:") and "230 documents" in message and "(for example m0, m1, m2)" in message
    assert "too many times" in message


def test_each_cause_gets_its_own_problem(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    listing = mails(3)
    bridge = FakeBridge(listing, {("m0", 0): make_pdf(NOTE, "WRONGPAN0"), ("m1", 0): make_pdf(NOTE, "WRONGPAN1")}, {})
    docs.sync_docs(db, bridge, PAN)         # m0 and m1: wrong password; m2: not in the blobs (KeyError)
    rows = problems(db)
    assert len(rows) == 2
    assert any("2 documents" in m for _, m, _ in rows) and any("1 document " in m for _, m, _ in rows)


def test_a_cause_that_repeats_next_sync_bumps_the_same_row(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    docs.sync_docs(db, QuotaBridge(mails(5)), PAN)
    docs.sync_docs(db, QuotaBridge(mails(5)), PAN)
    [(_, _, count)] = problems(db)
    assert count == 2


def test_the_cache_stops_calling_the_bridge_after_the_first_quota_error(tmp_path):
    inner = QuotaBridge(mails(230))
    cache = google.Cache(inner, tmp_path / "docs")
    db = store.open(tmp_path / "sp.duckdb")
    docs.sync_docs(db, cache, PAN)
    assert inner.calls == ["m0"]                # one call reached the bridge; the other 229 never did
    assert cache.quota_hit


def test_documents_the_quota_blocked_are_deferred_not_failed(tmp_path):
    inner = QuotaBridge(mails(230))
    db = store.open(tmp_path / "sp.duckdb")
    docs.sync_docs(db, google.Cache(inner, tmp_path / "docs"), PAN)
    assert problems(db) == [("gmail-quota", "Gmail daily limit reached: 230 documents wait for the next sync.", 1)]
    assert db.execute("select count(*) from documents").fetchone()[0] == 0          # so the next sync tries them
    docs.sync_docs(db, google.Cache(QuotaBridge(mails(230)), tmp_path / "docs2"), PAN)
    assert db.execute("select count(*) from fetch_log where source = 'docs'").fetchone()[0] == 0   # window did not move


def test_feed_reports_deferred_separately(tmp_path):
    cache = google.Cache(QuotaBridge(mails(3)), tmp_path / "docs")
    result = feed.fetch(cache, PAN, None)
    assert result.deferred == ["m0", "m1", "m2"] and result.failed == []


def test_a_cached_mail_is_still_read_after_the_quota_is_hit(tmp_path):
    inner = QuotaBridge(mails(2))
    cache = google.Cache(inner, tmp_path / "docs")
    cache.items = {}
    (cache.blobs / "m-m1-0").write_bytes(make_pdf(NOTE, PAN))
    result = feed.fetch(cache, PAN, None)
    assert result.deferred == ["m0"] and [h["id"] for h in result.handled] == ["m1"]
