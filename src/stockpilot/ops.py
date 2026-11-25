"""Ops: score old calls, check the system's health, open `self-heal` issues, publish status and archive.
Nothing here is resident: each function runs inside a systemd timer and returns. Network and shell
calls (`gh`, git remotes) are passed in or are plain git, so tests run on temp files and bare repos."""
import json
import re
import shutil
import subprocess
import tempfile
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import duckdb

from stockpilot.sources import exchange

from stockpilot.calls import record as record_mod
from stockpilot.jobs.due import CRUNCH_FROM_HOUR

TOKEN_WARN_DAYS = 14
DAILY_GRACE_HOUR = 20          # `sp daily` runs at 19:00; a missing run is only a fault after this
WAITING_UNTIL_HOUR = 23        # a daily run that waits for NSE is retried until then, then it is a fault
DECIDE_START_GRACE = timedelta(minutes=30)
DECIDE_RUNNING_LIMIT = timedelta(hours=3)
MIN_FREE_BYTES = 500 * 10**6
ARCHIVE_BRANCH = re.compile(r"archive(-[\w.]+)?")
GIT_ID = ["-c", "user.name=stockpilot", "-c", "user.email=stockpilot@localhost"]


# ---- doctor ------------------------------------------------------------------------------------

def _latest_trading_day(db, now: datetime) -> date:
    day = now.date() if now.hour >= DAILY_GRACE_HOUR else now.date() - timedelta(days=1)
    while not exchange.is_trading_day(db, day):
        day -= timedelta(days=1)
    return day


def _decide_fault(db, ingest_at: datetime, now: datetime) -> list[dict]:
    """The ingest for the expected day went well: the calls step after it must have too."""
    row = db.execute("select status, started_at from runs where job = 'daily_decide' and started_at >= ? "
                     "order by started_at desc, id desc limit 1", [ingest_at]).fetchone()
    if row and row[0] == "ok":
        return []
    if row and row[0] == "failed":
        return [{"key": "daily_decide-failed", "summary": "Today's calls failed",
                 "detail": "The last daily_decide run failed; see the problem log below."}]
    # gather's ingest lands in the afternoon; the crunch is only due from 19:00 (22:00 at the latest)
    since = row[1] if row else max(ingest_at, datetime.combine(ingest_at.date(), time(CRUNCH_FROM_HOUR)))
    waited = now - since
    if waited <= (DECIDE_RUNNING_LIMIT if row else DECIDE_START_GRACE):
        return []          # still running, or about to start (it follows the ingest in the same process)
    return [{"key": "daily_decide-stale", "summary": "No calls were made after the ingest",
             "detail": f"The ingest ran at {ingest_at}; "
                       + (f"the decide step started at {row[1]} and never finished." if row else "no decide step ran after it.")}]


def diagnose(db, cfg: dict, now: datetime, root: Path, free_bytes=None) -> list[dict]:
    """Everything wrong right now, as [{key, summary, detail}]. A key names one fault, so it is filed once."""
    found = []
    expected = _latest_trading_day(db, now)
    last = db.execute("select status, started_at, notes from runs where job = 'daily_ingest' "
                      "order by started_at desc, id desc limit 1").fetchone()
    if last is None or last[1].date() < expected:
        found.append({"key": "daily_ingest-stale", "summary": f"No daily run for {expected}",
                      "detail": f"The last daily_ingest run was {last[1] if last else 'never'}; one was due for {expected}."})
    elif last[0] == "failed":
        notes = json.loads(last[2] or "{}")
        found.append({"key": "daily_ingest-failed", "summary": "The daily run failed",
                      "detail": json.dumps(notes.get("failed", notes), indent=2, default=str)})
    elif last[0] == "waiting":        # the day's prices are not out yet; the run is retried until 23:00
        if now.hour >= WAITING_UNTIL_HOUR:
            note = json.loads(last[2] or "{}").get("note", "NSE has not published the day's prices.")
            found.append({"key": "daily_ingest-stale", "summary": f"NSE had not published {expected} by {WAITING_UNTIL_HOUR}:00",
                          "detail": f"{note} The daily run kept waiting and no calls were made for {expected}."})
    elif last[0] in ("ok", "partial"):
        found.extend(_decide_fault(db, last[1], now))
    for name, spec in (cfg.get("tokens") or {}).items():
        left = (date.fromisoformat(str(spec["issued"])) + timedelta(days=spec.get("lifetime_days", 365)) - now.date()).days
        if left <= TOKEN_WARN_DAYS:
            found.append({"key": f"token-{name}", "summary": f"{name} expires in {left} days",
                          "detail": f"Renew it ({left} days left) and update .env, then the vault."})
    free = (free_bytes or (lambda p: shutil.disk_usage(p).free))(root)
    if free < MIN_FREE_BYTES:
        found.append({"key": "disk-low", "summary": f"Only {free // 10**6} MB of disk left",
                      "detail": "Clear caches or old logs; the DuckDB file and data/ are the big ones."})
    for job, hours in (cfg.get("freshness") or {}).items():       # optional: other jobs that write run rows
        row = db.execute("select max(started_at) from runs where job = ? and status in ('ok', 'partial')",
                         [job]).fetchone()[0]
        if row is None or now - row > timedelta(hours=hours):
            found.append({"key": f"{job}-stale", "summary": f"{job} has not succeeded in {hours} hours",
                          "detail": f"Last good run: {row}."})
    return found


# ---- status and archive ----------------------------------------------------------------------

def build_status(db, cfg: dict, now: datetime, root: Path) -> dict:
    findings = diagnose(db, cfg, now, root)
    last_ok = {job: str(at) for job, at in db.execute(
        "select job, max(started_at) from runs where status in ('ok', 'partial', 'holiday') group by job").fetchall()}
    recent = [{"job": j, "status": s, "at": str(a)} for j, s, a in db.execute(
        "select job, status, started_at from runs order by started_at desc, id desc limit 10").fetchall()]
    holidays = [str(d) for (d,) in db.execute("select date from holidays where date >= ? and date <= ? order by date",
                                              [now.date() - timedelta(days=7), now.date() + timedelta(days=60)]).fetchall()]
    return {"generated_at": now.astimezone(timezone.utc).isoformat(), "ok": not findings, "findings": findings,
            "last_ok": last_ok, "recent_runs": recent, "holidays": holidays,
            "trading_day_today": exchange.is_trading_day(db, now.date()), "record": record_mod.summary(db)}


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout


def _has_branch(remote: str, branch: str) -> bool:
    """Exactly `refs/heads/<branch>`: a bare name would also match `feature/<branch>`."""
    return bool(subprocess.run(["git", "ls-remote", "--heads", remote, f"refs/heads/{branch}"], capture_output=True,
                               text=True, check=True).stdout.strip())


def push_status(remote: str, status: dict, branch: str = "status") -> None:
    """One commit, force-pushed: only the latest status matters."""
    with tempfile.TemporaryDirectory() as tmp:
        _git(tmp, "init", "-q", "-b", branch)
        Path(tmp, "status.json").write_text(json.dumps(status, indent=2, default=str))
        _git(tmp, "add", ".")
        _git(tmp, *GIT_ID, "commit", "-q", "-m", f"status {status['generated_at']}")
        _git(tmp, "push", "-q", "--force", remote, f"{branch}:{branch}")


def archive_payload(db, day: date, root: Path) -> dict | None:
    """The day's calls (and the brief the model was shown, if saved), read from the store; None when there are none.
    Pushing them is `archive_push`, which needs no database."""
    cols = [c[0] for c in db.execute("select * from calls limit 0").description]
    calls = [dict(zip(cols, r)) for r in db.execute("select * from calls where made_on = ? order by id", [day]).fetchall()]
    if not calls:
        return None
    for c in calls:
        for field in ("reasons", "risks", "news", "skeptic"):
            if isinstance(c.get(field), str):
                try:
                    c[field] = json.loads(c[field])
                except ValueError:
                    pass
    brief = Path(root) / "data" / "briefs" / f"{day}.json"
    return {"calls": calls, "brief": brief.read_text() if brief.exists() else None}


def archive_push(remote: str, day: date, payload: dict, branch: str = "archive") -> bool:
    """Append the day to the append-only archive branch. False if the day is already there.
    The branch is made on the first call as an orphan (its own history, no parent in common with main or a stage branch).
    Only a branch named `archive` or `archive-...` is ever pushed to, and never with force: if another machine made it a moment
    ago the push is refused and the day is tried again on the next run."""
    if not ARCHIVE_BRANCH.fullmatch(branch):
        raise ValueError(f"{branch!r} is not an archive branch; refusing to push to it")
    with tempfile.TemporaryDirectory() as tmp:
        if _has_branch(remote, branch):
            _git(tmp, "clone", "-q", "--depth", "1", "-b", branch, remote, "r")
            repo = Path(tmp, "r")
        else:
            repo = Path(tmp, "r")
            repo.mkdir()
            _git(repo, "init", "-q", "-b", branch)
        target = repo / str(day)
        if target.exists():
            return False
        target.mkdir()
        (target / "calls.json").write_text(json.dumps(payload["calls"], indent=2, default=str))
        if payload.get("brief"):
            (target / "brief.json").write_text(payload["brief"])
        _git(repo, "add", ".")
        _git(repo, *GIT_ID, "commit", "-q", "-m", f"archive {day}")
        _git(repo, "push", "-q", remote, f"refs/heads/{branch}:refs/heads/{branch}")   # never forced: history is the proof
    return True


def freeze_day(db, day: date) -> None:
    """The day's calls are in the archive: the forecast refuses to change them from now on."""
    db.execute("insert or replace into archived_days (day) values (?)", [day])


def archive(db, remote: str, day: date, root: Path, branch: str = "archive") -> bool:
    """Append the day's calls (and brief, if saved) to the archive branch. False if nothing to add."""
    payload = archive_payload(db, day, root)
    done = bool(payload) and archive_push(remote, day, payload, branch)
    if done:
        freeze_day(db, day)
    return done
