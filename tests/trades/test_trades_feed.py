import base64
import json
from datetime import date
from pathlib import Path

from pdfs import make_pdf
from stockpilot import store
from stockpilot.sources import google
from stockpilot.trades import feed, lots
from test_trades_documents import COIN_BUY, FIX, NOTE

PAN = "ABCDE1234F"
CAS_PDF_LINES = FIX.joinpath("cas_holdings.txt").read_text().splitlines()


class FakeBridge(google.Bridge):
    def __init__(self, listing, blobs, bodies):
        self.listing, self.blobs, self.bodies, self.asked, self.fetched = listing, blobs, bodies, [], []

    def list(self, since=None):
        self.asked.append(since)
        return self.listing

    def att(self, msg_id, index):
        self.fetched.append((msg_id, index))
        return google.Blob("x.pdf", "application/pdf", self.blobs[(msg_id, index)])

    def file(self, file_id):
        self.fetched.append(file_id)
        return google.Blob("tradebook.csv", "text/csv", self.blobs[file_id])

    def body(self, msg_id):
        self.fetched.append(msg_id)
        return self.bodies[msg_id]


def msg(id, frm, subject, attachments=0, mime="application/pdf"):
    return {"source": "gmail", "id": id, "from": frm, "subject": subject, "date": "2026-11-20T10:00:00Z",
            "attachments": [{"i": i, "name": "a", "mime": mime, "size": 1} for i in range(attachments)]}


def drive(id, name, mime="text/csv"):
    return {"source": "drive", "id": id, "name": name, "path": "Income Tax", "mime": mime}


def test_feed_routes_each_document_type_and_stores_trades(tmp_path):
    csv = FIX.joinpath("tradebook_mf.csv").read_bytes()
    bridge = FakeBridge(
        [msg("m1", "Zerodha <a@reportsmailer.zerodha.net>", "Combined Equity Contract Note for NZ4811 - Nov", 1),
         msg("m2", "Coin <a@coinmailer.zerodha.net>", "Coin by Zerodha - Allotment Report -  02-07-2025"),
         msg("m3", "CDSL <e@cdslstatement.com>", "CDSL Consolidated Account Statement (CAS) across Mutual Funds", 1),
         msg("m5", "Zerodha <a@alertsmailer.zerodha.net>", "Payment success"),
         drive("d1", "Tradebook Mutual fund.csv")],
        {("m1", 0): make_pdf(NOTE, PAN), ("m3", 0): make_pdf(CAS_PDF_LINES, PAN), "d1": csv},
        {"m2": COIN_BUY})
    result = feed.fetch(bridge, PAN, since="2026-01-01T00:00:00Z", isin_of=lambda name: "INF879O01027")
    assert sorted({t.source for t in result.trades}) == ["coin", "contract_note", "tradebook"]
    assert result.statements[0].closing["INE742F01042"] == 59.0
    assert result.ignored == [("m5", "payment confirmation")] and result.skipped == []
    assert "m5" not in bridge.fetched                      # ignored mail is never downloaded
    db = store.open(tmp_path / "t.duckdb")
    assert feed.store_all(db, result) == len(result.trades) - 1     # the Coin mail and the tradebook row are one purchase
    assert lots.rebuild(db).lots > 0


def test_first_sync_asks_for_all_history_not_the_bridge_default_of_400_days():
    bridge = FakeBridge([], {}, {})
    feed.fetch(bridge, PAN, since=None)
    assert bridge.asked == [feed.ALL_HISTORY]


def test_image_attachments_are_ignored_quietly_not_failed():
    bridge = FakeBridge([msg("m1", "Zerodha <a@reportsmailer.zerodha.net>", "Combined Equity Contract Note for NZ4811", 1,
                             mime="image/png")], {}, {})
    result = feed.fetch(bridge, PAN, since=None)
    assert result.failed == [] and result.trades == [] and bridge.fetched == []
    assert result.ignored == [("m1", "image attachment")]


def test_unknown_mail_is_skipped_and_named():
    bridge = FakeBridge([msg("m1", "Zerodha <a@zerodha.net>", "Our new feature")], {}, {})
    assert feed.fetch(bridge, PAN, since=None).skipped == ["m1"]


def test_unreadable_document_is_reported_not_fatal():
    bridge = FakeBridge([msg("m1", "Zerodha <a@zerodha.net>", "Contract note", 1)],
                        {("m1", 0): make_pdf(NOTE, "OTHERPAN00")}, {})
    result = feed.fetch(bridge, PAN, since=None)
    assert result.trades == [] and result.failed[0][0] == "m1" and "password" in result.failed[0][1]


def test_sync_docs_resolves_fund_isin_by_name_and_remembers_the_last_sync(tmp_path):
    from stockpilot.jobs import docs
    db = store.open(tmp_path / "t.duckdb")
    db.execute("insert into funds (scheme_code, isin_growth, name) values (1, 'INF879O01027',"
               " 'Parag Parikh Flexi Cap Fund - Direct Plan - Growth')")
    bridge = FakeBridge([msg("m2", "Coin <a@coinmailer.zerodha.net>", "Coin by Zerodha - Allotment Report -  02-07-2025")],
                        {}, {"m2": COIN_BUY})
    note = docs.sync_docs(db, bridge, PAN)
    assert "1 new trades" in note and bridge.asked == [feed.ALL_HISTORY]
    assert db.execute("select isin from trades").fetchall() == [("INF879O01027",)]
    docs.sync_docs(db, bridge, PAN)                      # second run is incremental, not all history again
    assert bridge.asked[1] != feed.ALL_HISTORY and bridge.asked[1] > "2020"


def test_a_failed_document_keeps_the_next_sync_from_skipping_it(tmp_path):
    from stockpilot.jobs import docs
    db = store.open(tmp_path / "t.duckdb")
    bridge = FakeBridge([msg("m1", "Zerodha <a@zerodha.net>", "Contract note", 1)], {("m1", 0): make_pdf(NOTE, "X")}, {})
    docs.sync_docs(db, bridge, PAN)
    docs.sync_docs(db, bridge, PAN)
    assert bridge.asked == [feed.ALL_HISTORY, feed.ALL_HISTORY]


def test_a_sync_with_no_new_or_changed_documents_downloads_and_parses_nothing(tmp_path):
    from stockpilot.jobs import docs
    db = store.open(tmp_path / "t.duckdb")
    bridge = FakeBridge([msg("m1", "Zerodha <a@reportsmailer.zerodha.net>", "Combined Equity Contract Note", 1)],
                        {("m1", 0): make_pdf(NOTE, PAN)}, {})
    docs.sync_docs(db, bridge, PAN)
    bridge.fetched.clear()
    note = docs.sync_docs(db, bridge, PAN)
    assert bridge.fetched == [] and note.startswith("Documents: no change")


def test_a_drive_file_changed_since_it_was_parsed_is_parsed_again(tmp_path):
    from stockpilot.jobs import docs
    db = store.open(tmp_path / "t.duckdb")
    item = {**drive("d1", "Tradebook Mutual fund.csv"), "modified": "2026-01-01T00:00:00Z"}
    bridge = FakeBridge([item], {"d1": FIX.joinpath("tradebook_mf.csv").read_bytes()}, {})
    docs.sync_docs(db, bridge, PAN)
    item["modified"] = "2026-02-01T00:00:00Z"
    bridge.fetched.clear()
    docs.sync_docs(db, bridge, PAN)
    assert bridge.fetched == ["d1"]


def test_a_pdf_sent_with_a_generic_mime_type_is_still_read():
    bridge = FakeBridge([msg("m3", "CDSL <e@cdslstatement.com>", "CDSL Consolidated Account Statement (CAS)", 1, mime="bin")],
                        {("m3", 0): make_pdf(CAS_PDF_LINES, PAN)}, {})
    bridge.listing[0]["attachments"][0]["name"] = "OCT2026_TXN.pdf"
    assert feed.fetch(bridge, PAN, since=None).statements[0].closing["INE742F01042"] == 59.0


def test_lots_are_checked_against_the_latest_depository_statement(tmp_path):
    from stockpilot.jobs import docs
    db = store.open(tmp_path / "t.duckdb")
    bridge = FakeBridge([msg("m3", "CDSL <e@cdslstatement.com>", "CDSL Consolidated Account Statement (CAS)", 1)],
                        {("m3", 0): make_pdf(CAS_PDF_LINES, PAN)}, {})
    note = docs.sync_docs(db, bridge, PAN)
    held = db.execute("select quantity from holding_statements where isin = 'INE742F01042'").fetchone()[0]
    assert held == 59.0
    assert "differ from the depository statement" in note
    assert db.execute("select count(*) from problems where message like 'INE742F01042:%59%lots hold 0%'").fetchone()[0] == 1
