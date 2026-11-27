"""The Documents Job writes each trade once, by key, and reads only files not yet done."""
from datetime import date

from stockpilot.jobs import documents
from stockpilot.trades.lots import Trade


class FakeDoor:
    def __init__(self):
        self.calls = []

    def job_start(self, kind, run_id):
        self.calls.append(("start", kind))

    def write_rows(self, dataset, run_id, rows):
        self.calls.append(("rows", dataset, rows))

    def job_finish(self, run_id, ok, result=None, error=None):
        self.calls.append(("finish", ok, result))

    def heartbeat(self, *a):
        self.calls.append(("beat",))


def test_trade_rows_carry_account_source_and_key():
    t = Trade("tradebook", "doc1", "stock", "AAA", None, "buy", date(2026, 11, 2), 3, 10.0)
    [row] = documents.trade_rows([t])
    assert row["account"] == "primary" and row["source"] == "tradebook" and row["trade_key"] == t.key
    assert row["trade_date"] == "2026-11-02"


def test_expected_vests_are_not_written():
    t = Trade("rsu_inference", "p1", "rsu", "BBB", None, "vest", date(2026, 11, 2), 3, None, status="expected")
    assert documents.trade_rows([t]) == []


def test_run_reads_new_files_only_and_writes_by_key(monkeypatch):
    from stockpilot.trades import feed
    seen = []

    def fake_fetch(bridge, pan, since, isin_of=None, done=frozenset(), limit=None):
        seen.append(set(done))
        r = feed.FeedResult()
        r.trades = [Trade("tradebook", "doc1", "stock", "AAA", None, "buy", date(2026, 11, 2), 3, 10.0)]
        r.handled = [{"id": "doc1", "version": "v1"}]
        return r

    monkeypatch.setattr(feed, "fetch", fake_fetch)
    door = FakeDoor()
    _, done = documents.run(door, object(), "PAN", set())
    assert done == {("doc1", "v1")}
    _, done2 = documents.run(door, object(), "PAN", done)
    assert seen[1] == {("doc1", "v1")}
    assert [c[0] for c in door.calls].count("rows") == 2
