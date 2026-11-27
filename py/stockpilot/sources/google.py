"""Client for the Apps Script bridge in google/bridge.gs. Read-only: list, file, att and body ops.
The fetch function is injected (default http.fetch) so tests never touch the network."""
import base64
import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from stockpilot.sources import http


class BridgeError(RuntimeError):
    pass


class Deferred(BridgeError):
    """Gmail's daily limit is used up: this document waits for the next sync. Not a failure."""


QUOTA_TEXT = "too many times"      # what the Apps Script bridge says when a daily quota is spent


def is_quota(err: Exception) -> bool:
    return QUOTA_TEXT in str(err).lower()


QUOTA_RESET_UTC_HOUR = 8     # Apps Script daily quotas reset at midnight Pacific time: 07:00 or 08:00 UTC


def next_reset(hit: datetime) -> datetime:
    """When Gmail's daily limit, hit at `hit`, is lifted: the next 08:00 UTC (a little after the reset, to be safe)."""
    reset = hit.astimezone(timezone.utc).replace(hour=QUOTA_RESET_UTC_HOUR, minute=0, second=0, microsecond=0)
    return reset if reset > hit else reset + timedelta(days=1)


@dataclass
class Blob:
    name: str
    mime: str
    data: bytes


class Bridge:
    def __init__(self, url: str, key: str, fetch=lambda u: http.fetch(u, attempts=2, timeout=150)):
        self.url, self.key, self._fetch = url, key, fetch

    def _call(self, op: str, **params):
        query = urlencode({"key": self.key, "op": op, **{k: v for k, v in params.items() if v is not None}})
        raw = self._fetch(f"{self.url}?{query}")
        if raw is None:
            raise BridgeError(f"bridge op {op}: no response")
        try:
            reply = json.loads(raw)
        except ValueError as err:
            raise BridgeError(f"bridge op {op}: reply is not JSON") from err
        if isinstance(reply, dict) and "error" in reply:
            raise BridgeError(f"bridge op {op}: {reply['error']}")
        return reply

    def ping(self) -> dict:
        return self._call("ping")

    def list(self, since: str | None = None) -> list[dict]:
        """New Drive files and Gmail messages since an ISO timestamp (everything when None)."""
        return self._call("list", since=since)

    def file(self, file_id: str) -> Blob:
        return _blob(self._call("file", id=file_id))

    def att(self, msg_id: str, index: int) -> Blob:
        return _blob(self._call("att", msg=msg_id, i=index))

    def body(self, msg_id: str) -> str:
        return self._call("body", msg=msg_id)["text"]


def _blob(reply: dict) -> Blob:
    return Blob(reply["name"], reply["mime"], base64.b64decode(reply["b64"]))


class Cache(Bridge):
    """The bridge with a private disk copy of everything it has fetched (default ~/sp-docs, outside git).
    A mail never changes, so it is downloaded once; a Drive file is downloaded again only when its modified time
    changes. The listing is merged into list.json, so a weekly incremental listing still returns every document
    ever seen, and a parser fix can re-read them all from disk without touching the Gmail quota."""

    def __init__(self, bridge: Bridge, root, now=lambda: datetime.now(timezone.utc)):
        from pathlib import Path
        self.bridge, self.root, self.now = bridge, Path(root), now
        self.blobs = self.root / "blobs"
        self.blobs.mkdir(parents=True, exist_ok=True)
        self.manifest = self.root / "list.json"
        self.items = {i["id"]: i for i in json.loads(self.manifest.read_text())} if self.manifest.exists() else {}
        self.stale = ""   # why the last listing came from disk instead of the bridge
        self.quota_file = self.root / "quota.json"
        self.quota_hit = self._quota_active()   # Gmail's daily limit is used up (this run or an earlier one): not asked again
        if self.quota_hit:
            self.stale = f"Gmail daily limit reached; asking again after {self._quota_until():%Y-%m-%d %H:%M} UTC"

    def _quota_until(self):
        try:
            return datetime.fromisoformat(json.loads(self.quota_file.read_text())["until"])
        except (OSError, ValueError, KeyError):
            return None

    def _quota_active(self) -> bool:
        until = self._quota_until()
        return bool(until and self.now() < until)

    def _note_quota(self) -> None:
        """Remember the limit across runs: the queue of waiting documents is not asked about again until it resets."""
        self.quota_hit = True
        _write(self.quota_file, json.dumps({"until": next_reset(self.now()).isoformat()}).encode())

    def ping(self) -> dict:
        return self.bridge.ping()

    def list(self, since: str | None = None) -> list[dict]:
        if self.quota_hit:
            return list(self.items.values())
        try:
            fresh = self.bridge.list(since=since)
        except BridgeError as err:   # e.g. the Gmail daily quota: parse what is on disk, list again next time
            if not self.items:
                raise
            if is_quota(err):
                self._note_quota()
            self.stale = str(err)
            return list(self.items.values())
        for item in fresh:
            self.items[item["id"]] = item
        _write(self.manifest, json.dumps(list(self.items.values())).encode())
        return list(self.items.values())

    def _ask(self, call, *args):
        """Ask the bridge; after the first reply that says the daily limit is used up, never ask again this run."""
        if self.quota_hit:
            raise Deferred("Gmail daily limit reached")
        try:
            return call(*args)
        except BridgeError as err:
            if not is_quota(err):
                raise
            self._note_quota()
            raise Deferred(str(err)) from err

    def file(self, file_id: str) -> Blob:
        path, meta = self.blobs / f"d-{file_id}", self.blobs / f"d-{file_id}.meta"
        modified = self.items.get(file_id, {}).get("modified")
        if path.exists() and meta.exists():
            info = json.loads(meta.read_text())
            if info.get("modified", modified) == modified:   # copies from before modified was recorded count as current
                return Blob(info["name"], info["mime"], path.read_bytes())
        blob = self._ask(self.bridge.file, file_id)
        _write(path, blob.data)
        _write(meta, json.dumps({"name": blob.name, "mime": blob.mime, "modified": modified}).encode())
        return blob

    def att(self, msg_id: str, index: int) -> Blob:
        path = self.blobs / f"m-{msg_id}-{index}"
        if path.exists():
            return Blob(path.name, "application/pdf", path.read_bytes())
        blob = self._ask(self.bridge.att, msg_id, index)
        _write(path, blob.data)
        return blob

    def body(self, msg_id: str) -> str:
        path = self.blobs / f"m-{msg_id}.txt"
        if path.exists():
            return path.read_text()
        text = self._ask(self.bridge.body, msg_id)
        _write(path, text.encode())
        return text


def _write(path, data: bytes) -> None:
    """Write whole or not at all: a timeout mid-download must not leave a truncated copy behind."""
    tmp = path.with_name(path.name + ".part")
    tmp.write_bytes(data)
    tmp.replace(path)
