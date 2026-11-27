"""A mock of the contract: answers only what the generated schemas allow and records every call."""

import json

from stockpilot.io.schemas import check

GOOD = {
    "ingest_write": lambda body: {"accepted": len(body["rows"]), "held_back": 0},
    "job_start": lambda body: {"run_id": body["run_id"], "started_at": "2026-11-27T10:00:00+05:30"},
    "job_finish": lambda body: {"ok": True},
    "market_status": lambda body: {"date": "2026-11-27", "is_trading_day": True, "reason": None},
    "heartbeat_write": lambda body: {"ok": True},
}
PATHS = {
    "/api/ingest": "ingest_write",
    "/api/jobs/start": "job_start",
    "/api/jobs/finish": "job_finish",
    "/api/market/status": "market_status",
    "/api/heartbeat": "heartbeat_write",
}


class MockContract:
    def __init__(self, fail_on: str | None = None):
        self.calls: list[tuple[str, dict | None]] = []
        self.fail_on = fail_on

    def __call__(self, method, url, headers, body):
        path = "/" + url.split("//", 1)[1].split("/", 1)[1]
        route = PATHS[path]
        payload = json.loads(body) if body else None
        if payload is not None:
            check(f"route.{route}.request", payload)  # the mock refuses what the contract refuses
        self.calls.append((route, payload))
        if route == self.fail_on:
            return 500, None
        return 200, GOOD[route](payload)
