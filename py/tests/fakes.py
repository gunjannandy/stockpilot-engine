"""Fakes for the Machine: every outside call is recorded in `m.log`, so a test can read what happened and in what order."""
from datetime import datetime
from pathlib import Path

from stockpilot import config


def make_config(root: Path, extra: str = ""):
    (root / "config").mkdir(parents=True, exist_ok=True)
    (root / "config" / "stockpilot.yaml").write_text("worker:\n  url: https://stockpilot-2zl.pages.dev\n" + extra)
    return config.load(root)


class Clock:
    def __init__(self, now: datetime):
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class EmptyBridge:
    """A Google bridge with nothing new."""
    stale = ""

    def list(self, since=None):
        return []


class QuietWorker:
    """A Worker with nothing queued and no Kite login today."""

    def get(self, path):
        return (409, None) if "/kite" in path else (200, [])

    def post(self, path, body):
        return 200, {}




def settle(m) -> None:
    """The store stamps runs with the wall clock, the Machine with its fake one: move this tick's rows to the fake now."""
    with m.db("settle") as db:
        db.execute("update runs set started_at = ?, finished_at = case when finished_at is null then null else ? end "
                   "where cast(started_at as date) = current_date", [m.clock.now, m.clock.now])


def queue_item(id_, kind, payload, by="father"):
    """One row as `GET /api/vm/queue` returns it."""
    return {"id": id_, "kind": kind, "payload": payload, "by": by, "at": "2026-11-23T08:00:00Z"}


def without_bhavcopy(fetch):
    """Wrap a fake `fetch(url)` so the NSE bhavcopy answers 404 (http.fetch returns None): the day is not published yet."""
    return lambda url: None if "NSE_CM" in url else fetch(url)
