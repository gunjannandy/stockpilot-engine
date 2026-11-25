"""The journal: what each job did (`runs`) and what went wrong (`problems`). Every job records through here,
so `sp doctor` and the Health tab read one shape.

A problem is keyed by (job, key); the key defaults to the message. While a problem is unresolved, saying it
again bumps its count and last_seen instead of adding a row, so a warning that repeats every sync is one line."""
import json
import os
from contextlib import contextmanager
from dataclasses import dataclass, field


def problem(db, job: str, message: str, severity: str = "warning", key: str | None = None,
            issue_url: str | None = None) -> None:
    key = key or message
    row = db.execute("select id from problems where job = ? and key = ? and resolution is null "
                     "order by id desc limit 1", [job, key]).fetchone()
    if row:
        db.execute("update problems set count = count + 1, last_seen = current_timestamp, message = ?, "
                   "severity = ? where id = ?", [message, severity, row[0]])
    else:
        db.execute("insert into problems (job, severity, message, key, issue_url) values (?, ?, ?, ?, ?)",
                   [job, severity, message, key, issue_url])


def prune_resolved(db, days: int = 30) -> int:
    """Drop resolved problems older than `days` (unresolved ones always stay). Cheap and idempotent: the tick runs it."""
    old = "resolution is not null and coalesce(last_seen, seen_at) < current_timestamp - to_days(?)"
    n = db.execute(f"select count(*) from problems where {old}", [days]).fetchone()[0]
    if n:
        db.execute(f"delete from problems where {old}", [days])
    return n


def start(db, job: str) -> int:
    return db.execute("insert into runs (job, status) values (?, 'running') returning id", [job]).fetchone()[0]


def finish(db, run_id: int, status: str, notes) -> None:
    db.execute("update runs set status = ?, finished_at = current_timestamp, notes = ? where id = ?",
               [status, json.dumps(notes, default=str), run_id])


@dataclass
class Run:
    db: object
    job: str
    id: int
    status: str = "ok"
    notes: dict = field(default_factory=dict)

    def warn(self, message: str, key: str | None = None) -> None:
        problem(self.db, self.job, message, "warning", key)

    def error(self, message: str, key: str | None = None) -> None:
        problem(self.db, self.job, message, "error", key)


@contextmanager
def run(db, job: str):
    """One `runs` row for the block. It ends `run.status` (default ok); an exception ends it failed, logs an error
    problem and propagates."""
    r = Run(db, job, start(db, job))
    try:
        yield r
    except Exception as err:
        problem(db, job, repr(err), "error")
        finish(db, r.id, "failed", {**r.notes, "error": str(err)})
        raise
    finish(db, r.id, r.status, r.notes)


def tracked(db, job: str, fn):
    """Run fn() as one run; its dict result becomes the notes."""
    with run(db, job) as r:
        result = fn()
        r.notes.update(result if isinstance(result, dict) else {"result": result})
    return result


# ---- jobs that found the database busy -------------------------------------------------------------

SKIPPED = "skipped.jsonl"


def record_skipped(db_dir, job: str, holder: dict | None) -> None:
    """A job that could not open the database writes one line beside it; the next successful open files it in `runs`."""
    from datetime import datetime, timezone
    from pathlib import Path
    folder = Path(db_dir)
    folder.mkdir(parents=True, exist_ok=True)
    line = json.dumps({"job": job, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "holder": holder})
    with open(folder / SKIPPED, "a") as f:
        f.write(line + "\n")


def flush_skipped(db) -> int:
    """Move the lines of skipped.jsonl into `runs` (status skipped, the holder in notes). Returns lines moved."""
    from datetime import datetime
    from pathlib import Path
    rows = db.execute("select path from duckdb_databases() where not internal and path is not null").fetchall()
    if not rows:
        return 0
    folder = Path(rows[0][0]).parent
    path = folder / SKIPPED
    if not path.exists():
        return 0
    taken = path.with_name(SKIPPED + f".{os.getpid()}")
    try:
        path.rename(taken)             # a job that is skipped right now starts a fresh file
    except FileNotFoundError:
        return 0
    moved = 0
    for text in taken.read_text().splitlines():
        try:
            line = json.loads(text)
            at = datetime.fromisoformat(line["at"]).replace(tzinfo=None)
        except (ValueError, KeyError):
            continue
        db.execute("insert into runs (job, started_at, finished_at, status, notes) values (?, ?, ?, 'skipped', ?)",
                   [line["job"], at, at, json.dumps({"holder": line.get("holder")})])
        moved += 1
    taken.unlink()
    return moved
