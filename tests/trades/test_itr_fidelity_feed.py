"""The feed reads ITR and Fidelity PDFs from Drive, stores them, and ignores (with a reason) the ones that cannot be read."""
from pathlib import Path

from stockpilot import store
from stockpilot.trades import feed
from pdfs import make_pdf
from test_trades_feed import FakeBridge, drive

FIX = Path(__file__).parents[1] / "fixtures" / "trades"
PAN = "AAAAA0000A"


def lines(name):
    return (FIX / name).read_text().splitlines()


def test_feed_stores_an_itr_acknowledgement_and_a_fidelity_year_end_report(tmp_path):
    items = [drive("i1", "2026 IncomeTaxAcknowledgement.pdf", "application/pdf"), drive("f1", "Fidelity 2025.pdf", "application/pdf")]
    blobs = {"i1": make_pdf(lines("itr_ack.txt"), PAN), "f1": make_pdf(lines("fidelity_year_end.txt"), PAN)}
    result = feed.fetch(FakeBridge(items, blobs, {}), PAN, None)
    assert result.failed == [] and result.ignored == [] and result.skipped == []
    db = store.open(tmp_path / "a.duckdb")
    feed.store_all(db, result)
    assert db.execute("select kind, assessment_year, total_income from itr_documents").fetchall() == [("acknowledgement", "2026-27", 2612465.0)]
    assert db.execute("select count(*) from fidelity_events where kind = 'vest'").fetchone()[0] == 4


def test_feed_ignores_with_a_reason_a_pdf_with_another_password_and_the_holdings_export(tmp_path):
    items = [drive("i1", "ITR Acknowledgement 2020.pdf", "application/pdf"), drive("f1", "Current Shares Fidelity.pdf", "application/pdf")]
    blobs = {"i1": make_pdf(lines("itr_ack.txt"), "OTHERPASS1"),
             "f1": make_pdf(["CSV Export", "Generated on: 31/12/2025 17:19:03", "Date ac", "quired"], PAN)}
    result = feed.fetch(FakeBridge(items, blobs, {}), PAN, None)
    assert result.failed == [] and sorted(i for i, _ in result.ignored) == ["f1", "i1"]
    assert dict(result.ignored)["i1"].startswith("another password")
    assert "holdings export" in dict(result.ignored)["f1"]


def test_a_return_that_cannot_be_read_is_a_failure_in_the_list_not_a_stop(tmp_path):
    items = [drive("i1", "ITR 2025 filled up.pdf", "application/pdf"), drive("i2", "2026 IncomeTaxAcknowledgement.pdf", "application/pdf")]
    blobs = {"i1": make_pdf(["Dear customer"], PAN), "i2": make_pdf(lines("itr_ack.txt"), PAN)}
    result = feed.fetch(FakeBridge(items, blobs, {}), PAN, None)
    assert [i for i, _ in result.failed] == ["i1"] and "not an income tax return" in result.failed[0][1]
    assert len(result.itr_docs) == 1
