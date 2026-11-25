"""Lane B step 1: Fidelity documents the feed once marked 'unknown' (they predate the Fidelity route) are read again from
the private disk copy, with no network, and their events are stored once however often it runs."""
import json
from pathlib import Path

from pdfs import make_pdf
from stockpilot import store
from stockpilot.jobs import fidelity

PAN = "AAAAA0000A"
FIX = Path(__file__).parents[1] / "fixtures" / "trades"


def cache(tmp_path, docs):
    """A ~/sp-docs lookalike: list.json plus one blob and .meta per Drive file."""
    root = tmp_path / "sp-docs"
    (root / "blobs").mkdir(parents=True)
    items = []
    for ident, name, lines in docs:
        items.append({"source": "drive", "id": ident, "name": name, "path": "Fidelity", "mime": "application/pdf",
                      "modified": "2026-03-21T06:42:21.000Z"})
        (root / "blobs" / f"d-{ident}").write_bytes(make_pdf(lines, PAN))
        (root / "blobs" / f"d-{ident}.meta").write_text(json.dumps({"name": name, "mime": "application/pdf",
                                                                    "modified": "2026-03-21T06:42:21.000Z"}))
    (root / "list.json").write_text(json.dumps(items))
    return root


def year_end():
    return (FIX / "fidelity_year_end.txt").read_text().splitlines()


def stale_row(db, ident, name):
    db.execute("insert into documents (id, source, kind, name, version, outcome, reason, trades) "
               "values (?, 'drive', 'fidelity', ?, '2026-03-21T06:42:21.000Z|5', 'unknown', '', 0)", [ident, name])


def test_a_document_marked_unknown_is_read_again_and_its_events_stored(db, tmp_path):
    root = cache(tmp_path, [("f1", "Fidelity 2025.pdf", year_end())])
    stale_row(db, "f1", "Fidelity 2025.pdf")
    out = fidelity.ingest(db, root, PAN)
    assert db.execute("select count(*) from fidelity_events where kind = 'vest'").fetchone()[0] == 4
    assert db.execute("select outcome, trades from documents where id = 'f1'").fetchone()[0] == "parsed"
    assert out["documents"] == 1 and out["events"] == 4 and out["failed"] == []


def test_running_it_twice_stores_no_duplicates(db, tmp_path):
    root = cache(tmp_path, [("f1", "Fidelity 2025.pdf", year_end())])
    fidelity.ingest(db, root, PAN)
    fidelity.ingest(db, root, PAN)
    assert db.execute("select count(*) from fidelity_events").fetchone()[0] == 4
    assert db.execute("select count(*) from documents where id = 'f1'").fetchone()[0] == 1


def test_a_document_that_cannot_be_read_is_named_not_hidden(db, tmp_path):
    root = cache(tmp_path, [("f1", "Fidelity 2025.pdf", ["Dear customer"]),
                            ("f2", "Current Shares Fidelity.pdf", ["CSV Export", "Date ac", "quired"])])
    out = fidelity.ingest(db, root, PAN)
    assert [i for i, _ in out["failed"]] == ["f1"]
    assert [i for i, _ in out["ignored"]] == ["f2"] and "holdings export" in out["ignored"][0][1]
    assert db.execute("select count(*) from fidelity_events").fetchone()[0] == 0


def test_only_fidelity_files_are_touched_and_nothing_else_in_the_cache_is_read(db, tmp_path):
    root = cache(tmp_path, [("f1", "Fidelity 2025.pdf", year_end()), ("x1", "Payslip March.pdf", ["whatever"])])
    out = fidelity.ingest(db, root, PAN)
    assert out["documents"] == 1
    assert db.execute("select count(*) from documents where id = 'x1'").fetchone()[0] == 0
