"""Fidelity documents from the private disk copy (`~/sp-docs`), with no network and no Gmail quota.

Why this exists: the feed marks a document handled by its Drive modified time plus the parser version. The nine Fidelity
PDFs were handled on 22 Nov, before the feed knew the Fidelity route, so they sat in `documents` as "unknown" with no
events, and nothing asked for them again. This reads exactly the Fidelity files of the disk copy, parses them, and stores
their events (a document's events replace the rows its Drive id stored before, so a second run adds nothing)."""
import json
from pathlib import Path

from stockpilot.sources import google
from stockpilot.trades import feed


class DiskBridge(google.Bridge):
    """Lists and reads only what the disk copy holds; any other call is an error, so the network is never reached."""

    def __init__(self, root):
        self.root = Path(root).expanduser()
        manifest = self.root / "list.json"
        items = json.loads(manifest.read_text()) if manifest.exists() else []
        self.items = [i for i in items if i.get("source") == "drive" and feed.classify_drive(i) == "fidelity"]

    def list(self, since=None):
        return self.items

    def file(self, file_id: str) -> google.Blob:
        path, meta = self.root / "blobs" / f"d-{file_id}", self.root / "blobs" / f"d-{file_id}.meta"
        if not (path.exists() and meta.exists()):
            raise google.BridgeError(f"{file_id} is not in the disk copy")
        info = json.loads(meta.read_text())
        return google.Blob(info["name"], info["mime"], path.read_bytes())


def ingest(db, root, pan: str) -> dict:
    """Read every Fidelity file of the disk copy again and store its events. Returns what happened, by document."""
    result = feed.fetch(DiskBridge(root), pan, None)
    feed.store_all(db, result)
    for row in result.handled:
        db.execute("insert or replace into documents (id, source, kind, name, version, outcome, reason, trades) "
                   "values ($id, $source, $kind, $name, $version, $outcome, $reason, $trades)", row)
    events = sum(len(doc.events) for doc, _ in result.fidelity_docs)
    return {"documents": len(result.handled), "events": events, "ignored": result.ignored, "failed": result.failed}
