"""The write side of the contract: ingest door, Job start and finish, the day's market status.

Every body is checked against the contract's JSON Schema before it leaves and after it returns. The
transport is injectable so tests talk to a mock of the contract, never the network. Broker code is
elsewhere; nothing here can place an order.
"""

import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from .clock import ist_now, ist_text
from .schemas import check, validate_row

# (method, url, headers, body) -> (status, parsed json)
Transport = Callable[[str, str, dict[str, str], bytes | None], tuple[int, object]]


class DoorError(RuntimeError):
    pass


def urllib_transport(method: str, url: str, headers: dict[str, str], body: bytes | None) -> tuple[int, object]:
    # Cloudflare refuses Python's default User-Agent on workers.dev (403, error code 1010).
    req = urllib.request.Request(url, data=body, headers={"user-agent": "stockpilot-job", **headers}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as res:  # noqa: S310 (https endpoint from config)
            return res.status, json.loads(res.read() or b"null")
    except urllib.error.HTTPError as err:
        return err.code, None


def new_run_id(kind: str, now: datetime | None = None) -> str:
    return f"{kind}-{(now or ist_now()).strftime('%Y%m%d')}-{uuid.uuid4().hex[:8]}"


@dataclass
class Door:
    base_url: str
    key: str
    transport: Transport = urllib_transport

    @classmethod
    def from_env(cls) -> "Door":
        return cls(os.environ["STOCKPILOT_API_URL"].rstrip("/"), os.environ["STOCKPILOT_INGEST_KEY"])

    def _call(self, route: str, method: str, path: str, payload: dict | None) -> object:
        if payload is not None:
            check(f"route.{route}.request", payload)
        body = json.dumps(payload).encode() if payload is not None else None
        headers = {"content-type": "application/json"}
        if body is not None:
            headers["x-signature"] = hmac.new(self.key.encode(), body, hashlib.sha256).hexdigest()
        else:
            headers["x-signature"] = hmac.new(self.key.encode(), b"", hashlib.sha256).hexdigest()
        status, data = self.transport(method, self.base_url + path, headers, body)
        if status >= 300:
            raise DoorError(f"{method} {path} answered {status}")
        check(f"route.{route}.response", data)
        return data

    def write_rows(self, dataset: str, run_id: str, rows: list[dict]) -> dict:
        """Validate every row first; one bad row stops the batch before anything is sent."""
        for row in rows:
            validate_row(dataset, row)
        return self._call("ingest_write", "POST", "/api/ingest", {"dataset": dataset, "run_id": run_id, "rows": rows})  # type: ignore[return-value]

    def job_begin(self, kind: str, run_id: str, subject: str = "all") -> dict:
        return self._call("job_begin", "POST", "/api/job/begin", {"kind": kind, "subject": subject, "run_id": run_id})  # type: ignore[return-value]

    def job_end(self, run_id: str, ok: bool, result: str | None = None, error: str | None = None) -> dict:
        body = {"run_id": run_id, "status": "done" if ok else "failed", "result": result, "error": error}
        return self._call("job_end", "POST", "/api/job/end", body)  # type: ignore[return-value]

    def market_status(self) -> dict:
        return self._call("market_status", "GET", "/api/market/status", None)  # type: ignore[return-value]

    def heartbeat(self, part: str, version: str, ok: bool, error: str | None, next_expected_by: datetime | None) -> dict:
        body = {
            "part": part,
            "version": version,
            "at": ist_text(ist_now()),
            "ok": ok,
            "error": error,
            "next_expected_by": ist_text(next_expected_by) if next_expected_by else None,
        }
        return self._call("heartbeat_write", "POST", "/api/heartbeat", body)  # type: ignore[return-value]
