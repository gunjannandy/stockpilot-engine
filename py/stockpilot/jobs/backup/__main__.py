"""`python -m stockpilot.jobs.backup backup|drill`: what the private workflows run.

backup reads production D1 and pushes the vault; drill restores the vault into the preview D1. Settings come from the
workflow's environment; nothing is printed that came from a table.
"""
import hashlib
import hmac
import json
import os
import sys
import tempfile
from pathlib import Path

from stockpilot import vault
from stockpilot.heartbeat import beat as send_beat
from stockpilot.io import Door
from stockpilot.jobs import backup as job
from stockpilot.jobs.backup.d1 import D1


def _door_report(door: Door):
    def report(body: dict) -> None:
        raw = json.dumps(body).encode()
        headers = {"content-type": "application/json", "x-signature": hmac.new(door.key.encode(), raw, hashlib.sha256).hexdigest()}
        status, _ = door.transport("POST", door.base_url + "/api/backup", headers, raw)
        if status >= 300:
            raise RuntimeError(f"POST /api/backup answered {status}")
    return report


def main(argv: list[str]) -> int:
    which = argv[1] if len(argv) > 1 else ""
    env, door = os.environ, Door.from_env()
    remote = env["VAULT_REMOTE"]

    def beat(part, ok, error=None):
        send_beat(door, part, ok=ok, error=error, every=job.DUE[part])

    def report(body):
        try:
            _door_report(door)(body)
        except Exception as err:  # noqa: BLE001 (a lost report must not hide the Job's own result; the beat still goes)
            print(f"report not sent: {type(err).__name__}", file=sys.stderr)

    work = Path(tempfile.mkdtemp(prefix="sp-d1-")) / "w"
    if which == "backup":
        keys = vault.Keys.load(Path(env.get("VAULT_KEYS", "config")))
        source = D1(env["CF_ACCOUNT_ID"], env["D1_PRODUCTION_ID"], env["CF_D1_READ_TOKEN"])
        job.backup(source, remote, keys, work, report, beat)
    elif which == "drill":
        target = D1(env["CF_ACCOUNT_ID"], env["D1_PREVIEW_ID"], env["CF_D1_PREVIEW_TOKEN"])
        job.drill(target, remote, env["VAULT_PASSWORD"], work, report, beat)
    else:
        print("usage: python -m stockpilot.jobs.backup backup|drill", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
