"""Signed calls to the Worker's Job runtime and publishing door.

`Door` (stockpilot.io) owns the key and the transport; this client reuses both, so tests talk to a fake
Worker and never the network. Answers come back as (status, body): a 409 (duplicate) or a 429 (cap
reached) is an answer a Job acts on, not an error.
"""
import hashlib
import hmac
import json
from dataclasses import dataclass

from stockpilot.io import Door


class JobRefused(RuntimeError):
    """The Worker refused to start the Job: a duplicate, a lock held by another run, or a paused kind."""

    def __init__(self, status: int, reason: str):
        super().__init__(f"{status}: {reason}")
        self.status, self.reason = status, reason


@dataclass
class JobClient:
    door: Door

    def post(self, path: str, payload: dict | None = None, method: str = "POST") -> tuple[int, dict]:
        body = json.dumps(payload).encode() if payload is not None else None
        sig = hmac.new(self.door.key.encode(), body or b"", hashlib.sha256).hexdigest()
        headers = {"content-type": "application/json", "x-signature": sig}
        status, data = self.door.transport(method, self.door.base_url + path, headers, body)
        return status, data if isinstance(data, dict) else {}

    def _ok(self, path: str, payload: dict | None = None, method: str = "POST") -> dict:
        status, data = self.post(path, payload, method)
        if status >= 300:
            raise RuntimeError(f"{method} {path} answered {status}: {data.get('error') or data.get('reason') or ''}")
        return data

    def begin(self, kind: str, run_id: str, *, subject: str = "all", day: str | None = None,
              start: str | None = None, end: str | None = None, rerun: bool = False) -> dict:
        body: dict = {"kind": kind, "subject": subject, "run_id": run_id}
        for key, value in (("day", day), ("from", start), ("to", end)):
            if value:
                body[key] = value
        if rerun:
            body["rerun"] = True
        status, data = self.post("/api/job/begin", body)
        if status in (409, 423):
            raise JobRefused(status, data.get("error", "refused"))
        if status >= 300:
            raise RuntimeError(f"begin answered {status}: {data.get('error', '')}")
        return data

    def end(self, run_id: str, ok: bool, result: str | None = None, error: str | None = None) -> dict:
        return self._ok("/api/job/end", {"run_id": run_id, "status": "done" if ok else "failed",
                                         "result": result, "error": error})

    def publish_rows(self, dataset: str, run_id: str, rows: list[dict], *, source: str, fetched_at: str,
                     as_of: str) -> dict:
        return self._ok("/api/publish/rows", {"dataset": dataset, "run_id": run_id, "source": source,
                                              "fetched_at": fetched_at, "as_of": as_of, "rows": rows})

    def publish_finish(self, dataset: str, run_id: str, **extra) -> dict:
        return self._ok("/api/publish/finish", {"dataset": dataset, "run_id": run_id, **extra})

    def market_status(self, day: str | None = None) -> dict:
        return self._ok("/api/market/status" + (f"?date={day}" if day else ""), None, "GET")
