from stockpilot.sources import google


class Inner(google.Bridge):
    def __init__(self, listing):
        self.listing, self.calls = listing, []

    def list(self, since=None):
        self.calls.append(("list", since))
        return self.listing

    def att(self, msg_id, index):
        self.calls.append(("att", msg_id))
        return google.Blob("a.pdf", "application/pdf", b"%PDF")

    def file(self, file_id):
        self.calls.append(("file", file_id))
        return google.Blob("t.csv", "text/csv", b"trade_type")

    def body(self, msg_id):
        self.calls.append(("body", msg_id))
        return "hello"


def test_a_cached_document_is_never_downloaded_twice(tmp_path):
    inner = Inner([])
    cache = google.Cache(inner, tmp_path)
    assert cache.att("m1", 0).data == b"%PDF" and cache.body("m1") == "hello"
    again = google.Cache(inner, tmp_path)
    assert again.att("m1", 0).data == b"%PDF" and again.body("m1") == "hello"
    assert inner.calls == [("att", "m1"), ("body", "m1")]


def test_the_listing_keeps_everything_seen_before_and_a_changed_drive_file_is_fetched_again(tmp_path):
    old = {"source": "drive", "id": "d1", "name": "t.csv", "modified": "2026-01-01"}
    inner = Inner([old, {"source": "gmail", "id": "m1", "subject": "x", "attachments": []}])
    cache = google.Cache(inner, tmp_path)
    cache.list(since="2015")
    cache.file("d1")
    inner.listing = [{**old, "modified": "2026-02-01"}]            # the incremental listing holds only the change
    listing = google.Cache(inner, tmp_path).list(since="2026-01-15")
    assert sorted(i["id"] for i in listing) == ["d1", "m1"]
    assert [i["modified"] for i in listing if i["id"] == "d1"] == ["2026-02-01"]
    google.Cache(inner, tmp_path).file("d1")
    assert [c for c in inner.calls if c[0] == "file"] == [("file", "d1"), ("file", "d1")]


def test_when_the_bridge_is_out_of_quota_the_cached_listing_is_used_and_the_gap_is_noted(tmp_path):
    inner = Inner([{"source": "gmail", "id": "m1", "subject": "x", "attachments": []}])
    google.Cache(inner, tmp_path).list(since="2015")

    def broke(since=None):
        raise google.BridgeError("bridge op list: Service invoked too many times for one day: gmail.")
    inner.list = broke
    cache = google.Cache(inner, tmp_path)
    assert [i["id"] for i in cache.list(since="2026")] == ["m1"]
    assert "too many times" in cache.stale
