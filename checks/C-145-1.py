"""C-145-1: docker compose smoke runs the Ping path on Node and SQLite.

Docker itself is not needed in CI: the compose services are the same three commands, so the smoke
starts the Node server on SQLite (the `api` service), runs the Python Ping Job against it (the
`ping-job` service), and reads the row and the heartbeat back.
"""
import json
import os
import re
import socket
import subprocess
import time
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
KEY = "local-development-key-0123456789abcdef"
HEALTH = "local-health-secret-0123456789"


def get(url, headers=None):
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=10) as r:
        return json.loads(r.read())


def test_compose_file_declares_the_three_services_on_node_and_sqlite():
    text = (ROOT / "docker-compose.yml").read_text()
    services = re.findall(r"^  ([a-z-]+):\n    image:", text, re.M)
    assert services == ["web", "api", "ping-job"]
    assert "SQLITE_PATH" in text and "stockpilot.jobs.ping" in text and "node:24" in text
    code = "\n".join(l for l in text.splitlines() if not l.lstrip().startswith("#")).lower()
    assert "cloudflare" not in code and "wrangler" not in code


@pytest.fixture()
def server(tmp_path):
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    env = {**os.environ, "PORT": str(port), "SQLITE_PATH": str(tmp_path / "sp.db"),
           "INGEST_HMAC_KEY": KEY, "HEALTH_SECRET": HEALTH, "APP_VERSION": "local"}
    proc = subprocess.Popen(["pnpm", "--filter", "@stockpilot/api", "start"], cwd=ROOT, env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    url = f"http://127.0.0.1:{port}"
    try:
        for _ in range(100):
            try:
                get(f"{url}/api/status")
                break
            except OSError:
                time.sleep(0.3)
        else:
            raise AssertionError("the Node server did not start")
        yield url
    finally:
        proc.terminate()
        proc.wait(timeout=10)


def test_ping_path_runs_on_node_and_sqlite(server):
    from stockpilot.io import Door
    from stockpilot.jobs.ping import run

    assert get(f"{server}/api/ping") == {"latest": None, "count": 0}
    run(Door(server, KEY))
    ping = get(f"{server}/api/ping")
    assert ping["count"] == 1 and ping["latest"]["source"] == "job"
    health = get(f"{server}/api/health", {"x-health-secret": HEALTH})
    job = next(p for p in health["parts"] if p["part"] == "job.ping")
    assert job["status"] == "green" and job["version"] is not None
