"""The Machine: everything a job reaches outside for, in one object, so tests build one from fakes.

Phase rule: network calls, the runner, `wrangler` and git or gh pushes run with the database closed. A job gets a
`Lease` from `machine.db(job)`: it opens the store on first use and `suspend()` lets the writer lock go, taking it
back on the next use. `lease.releasing(fetcher)` wraps a fetcher so every network call happens with the lock free."""
from contextlib import contextmanager
from dataclasses import dataclass, field
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from stockpilot import store


class Lease:
    """A database handle that can let go of the writer lock and take it back on its next use."""

    def __init__(self, opener: Callable):
        self._opener, self._db = opener, None

    def _live(self):
        if self._db is None:
            self._db = self._opener()
        return self._db

    def __getattr__(self, name):          # only for names Lease does not have: everything the connection does
        return getattr(self._live(), name)

    def suspend(self) -> None:
        db, self._db = self._db, None
        if db is not None:
            store.close(db)

    close = suspend

    @property
    def held(self) -> bool:
        return self._db is not None

    def releasing(self, outside: Callable) -> Callable:
        """`outside` (a fetcher, a bridge call) with the lock let go first: the next use of the database takes it again."""
        def wrapped(*args, **kwargs):
            self.suspend()
            return outside(*args, **kwargs)
        return wrapped


@dataclass
class Machine:
    cfg: object
    clock: Callable[[], datetime] = datetime.now
    fetch: Callable | None = None                # (url) -> bytes | None
    fetch_json: Callable | None = None           # (path) -> parsed NSE JSON
    fetch_file: Callable | None = None           # (url, max_bytes) -> bytes | None, for filings
    worker: object | None = None                 # kite.Worker
    bridge: Callable | None = None               # () -> (bridge, pan)
    analyse: Callable | None = None              # (brief, role, runners) -> decisions
    runners: list = field(default_factory=lambda: ["claude"])
    yahoo: Callable | None = None                # (symbol) -> fundamentals data
    yahoo_history: Callable | None = None        # (symbols, start) -> closes
    deploy: Callable | None = None               # () -> note; raises when wrangler fails
    push_status: Callable | None = None          # (status dict) -> None
    push_archive: Callable | None = None         # (day, payload) -> bool
    push_vault: Callable | None = None           # () -> None
    upload_market: Callable | None = None        # (tag, files) -> None
    gh: Callable | None = None                   # gh(*args) -> stdout
    git: Callable | None = None                  # git(*args) -> stdout
    start_tick: Callable | None = None           # () -> None: ask systemd to run a tick now
    sleep: Callable = time.sleep                 # between Yahoo calls
    wait_s: float = 600.0                        # how long a job waits for the lock (a doctor run is short)
    poll_s: float = 5.0

    @property
    def root(self) -> Path:
        return Path(self.cfg.root)

    @property
    def db_path(self) -> Path:
        return self.root / self.cfg.get("store.path", "data/stockpilot.duckdb")

    def _open(self, job: str, wait_s: float | None):
        return store.open(self.db_path, job=job, wait_s=self.wait_s if wait_s is None else wait_s, poll_s=self.poll_s)

    @contextmanager
    def db(self, job: str, wait_s: float | None = None):
        """The store, locked for `job`. Raises store.Busy when another process holds it past the wait."""
        lease = Lease(lambda: self._open(job, wait_s))
        lease._live()
        try:
            yield lease
        finally:
            lease.close()


def start_tick(root, run=None, popen=None) -> None:
    """Ask systemd to run a tick now (a rerun was asked for). Where that cannot be done (tests, a dev machine, no sudo rule)
    start `sp tick` as a subprocess; either way the tick finds the rerun file."""
    import subprocess
    import sys
    run, popen = run or subprocess.run, popen or subprocess.Popen
    try:
        done = run(["sudo", "-n", "systemctl", "start", "--no-block", "sp-tick.service"],
                   capture_output=True, text=True, timeout=60)
        if done.returncode == 0:
            return
    except (OSError, subprocess.TimeoutExpired):
        pass
    popen([sys.executable, "-m", "stockpilot.cli", "--root", str(root), "tick"])


def real(cfg) -> Machine:
    """The machine as production wires it."""
    import os
    import subprocess
    from functools import partial
    from stockpilot import backup, ops
    from stockpilot.sources import fundamentals, http, kite, nse_api, usprices
    from stockpilot.calls import runner
    from stockpilot.jobs import docs, doctor, ship
    from stockpilot.sources import filings

    first = cfg.get("runner", "claude")
    runners = [first] + [r for r in ("claude", "agy") if r != first]
    env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": cfg.secret("CLAUDE_CODE_OAUTH_TOKEN") or ""}
    analyse = partial(runner.analyse, env=env, models=cfg.get("runner_models"))
    session = nse_api.Session()
    fetch_json, fetch_file = filings.fetchers(session)
    key = cfg.secret("SP_VM_KEY")

    def git(*args):
        return subprocess.run(["git", *args], cwd=cfg.root, capture_output=True, text=True, check=True).stdout

    def remote() -> str:
        return git("remote", "get-url", cfg.get("vault.remote", "origin")).strip()

    def push_vault():
        from stockpilot import vault
        keys = vault.Keys.load(cfg.root / "config")
        vault.push(cfg.root, remote(), keys, cfg.get("vault.paths", ["private", ".env"]))

    return Machine(
        cfg=cfg, fetch=http.fetch, fetch_json=fetch_json, fetch_file=fetch_file,
        worker=kite.Worker(cfg.get("worker.url"), key) if key else None,
        bridge=lambda: docs.bridge_from(cfg), analyse=lambda b, role, rs: analyse(b, role, rs), runners=runners,
        yahoo=fundamentals.yahoo, yahoo_history=usprices.yahoo_history, deploy=lambda: ship.deploy_safe(cfg),
        push_status=lambda status: ops.push_status(remote(), status),
        push_archive=lambda day, payload: ops.archive_push(remote(), day, payload),
        push_vault=push_vault, upload_market=backup.gh_upload, gh=doctor.gh_cli(cfg.root), git=git,
        start_tick=lambda: start_tick(cfg.root))
