"""Fakes for the Machine: every outside call is recorded in `m.log`, so a test can read what happened and in what order."""
from datetime import datetime
from pathlib import Path

from stockpilot import config
from stockpilot.machine import Machine


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


def make_machine(root: Path, now: datetime | None = None, **overrides) -> Machine:
    """A Machine over a temp project; every outside call is a recording fake unless the test replaces it.
    `m.log` lists the calls in order; `m.clock.now` can be moved."""
    from test_jobs import fetch as _fetch, fetch_json
    def fetch(url):   # R4: the Google News feed answers with no items; everything else comes from the saved files
        return b"<rss version='2.0'><channel></channel></rss>" if "news.google.com" in url else _fetch(url)
    cfg = make_config(root, overrides.pop("extra", ""))
    clock = Clock(now or datetime(2026, 11, 20, 19, 3))
    log: list = []

    def recorded(name, result=None):
        def call(*args, **kwargs):
            log.append(name)
            return result
        return call

    base = dict(cfg=cfg, clock=clock, worker=QuietWorker(), poll_s=0.05, wait_s=0.0, fetch=fetch, fetch_json=fetch_json,
                bridge=lambda: (EmptyBridge(), "PAN"), runners=["fake"], sleep=lambda s: None,
                deploy=lambda: log.append("deploy") or "Dashboard deployed.",
                push_status=lambda status: log.append("push_status"),
                push_archive=lambda day, payload: log.append("push_archive") or True,
                push_vault=recorded("push_vault"), upload_market=recorded("upload_market"),
                start_tick=recorded("start_tick"), gh=lambda *a: "[]", git=lambda *a: "")
    base.update(overrides)
    m = Machine(**base)
    m.log = log
    return m


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
