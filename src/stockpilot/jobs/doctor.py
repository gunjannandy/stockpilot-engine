"""The doctor: file one `self-heal` issue per new fault, publish status, and act on rerun requests. It is its own
hourly timer, so it still runs when a tick hangs; when the database is busy it pushes a heartbeat from the lock file."""
import json
import re
import shutil
import subprocess
import tempfile
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from stockpilot import journal, ops, store
from stockpilot.jobs import due, ship, tick

JOB_OF = {"daily_ingest": "daily", "daily_decide": "daily", "crunch": "daily", "nav": "nav", "weekly": "weekly", "kite": "kite",
          "queue": "queue"}
HEAL_LABEL = "self-heal"
RERUN_LABEL = "rerun-requested"


def gh_cli(root: Path | str = "."):
    def run(*args):
        return subprocess.run(["gh", *args], cwd=root, capture_output=True, text=True, check=True).stdout
    return run


def _issue_body(finding: dict, db) -> str:
    problems = db.execute("select seen_at, job, message from problems where job != 'doctor' "
                          "order by seen_at desc limit 5").fetchall()
    log = "\n".join(f"- {t} {j}: {m[:400]}" for t, j, m in problems) or "- none logged"
    job = finding["key"].split("-")[0]
    job = job if job in JOB_OF else "none"
    return (f"{finding['summary']}\n\njob: {job}\nkey: {finding['key']}\n\n```\n{finding['detail']}\n```\n\n"
            f"Recent problem log:\n{log}\n\nTried so far: in-job retries and fallbacks; `sp doctor` then opened this issue.\n"
            f"Outage? Label it `{RERUN_LABEL}` and the VM reruns the job. Bug? Open a fix PR with a test.")


def doctor(db, cfg: dict, now: datetime, root: Path, gh) -> int:
    """File one `self-heal` issue per new fault; mark faults that cleared. Returns issues opened."""
    from stockpilot.book import units
    units.record(db)
    found = {f["key"]: f for f in ops.diagnose(db, cfg, now, root) + units.findings(db)}
    open_keys = {k for (k,) in db.execute(
        "select message from problems where job = 'doctor' and resolution is null").fetchall()}
    for key in open_keys - set(found):
        db.execute("update problems set resolution = 'cleared' where job = 'doctor' and message = ? "
                   "and resolution is null", [key])
    opened = 0
    for key, finding in found.items():
        if key in open_keys:
            continue
        title = f"[{HEAL_LABEL}] {key}"
        existing = json.loads(gh("issue", "list", "--label", HEAL_LABEL, "--state", "open",
                                 "--json", "number,title", "--search", key) or "[]")
        url = None
        if not any(key in i.get("title", "") for i in existing):
            url = gh("issue", "create", "--label", HEAL_LABEL, "--title", title,
                     "--body", _issue_body(finding, db)).strip()
            opened += 1
        journal.problem(db, "doctor", key, "error", issue_url=url or "existing")
    return opened


def request_rerun(m, job: str) -> int:
    """Ask for a job to run again: a file the next tick reads, and a tick started now (systemd, else a subprocess).
    The tick runs the job with the database to itself, so the doctor must have let go of it first."""
    due.ask_rerun(m.root, job)
    if m.start_tick:
        m.start_tick()
    return 0


def apply_reruns(gh, run_job) -> int:
    """Issues the self-heal Action labelled `rerun-requested`: run the named job, comment, drop the label."""
    done = 0
    for issue in json.loads(gh("issue", "list", "--label", RERUN_LABEL, "--state", "open",
                               "--json", "number,body,labels") or "[]"):
        match = re.search(r"^job: (\w+)", issue.get("body", ""), re.M)
        job = JOB_OF.get(match.group(1)) if match else None
        number = str(issue["number"])
        if job:
            rc = run_job(job)
            gh("issue", "comment", number, "--body", f"Started `sp {job}`: " + ("it runs on its own now; the Health tab shows how it went." if rc == 0 else f"exit code {rc}."))
        else:
            gh("issue", "comment", number, "--body", "No job named in the issue body, so nothing was rerun.")
        gh("issue", "edit", number, "--remove-label", RERUN_LABEL)
        done += 1
    return done


def heartbeat(holder: dict | None, now: datetime) -> dict:
    """What the doctor pushes when another job holds the database: built without it, so the watchdog still sees life."""
    return {"generated_at": now.astimezone(timezone.utc).isoformat(), "busy": holder, "ok": None}


def run(m, push: bool = True, reruns: bool = True) -> dict:
    now = m.clock()
    try:
        with m.db("doctor", wait_s=0) as db:
            opened = doctor(db, ship.ops_cfg(m.cfg), now, m.root, m.gh)
            status = ops.build_status(db, ship.ops_cfg(m.cfg), now, m.root) if push else None
    except store.Busy as err:   # no fault: say we are alive, from the lock file, and let the job finish
        journal.record_skipped(m.db_path.parent, "doctor", err.holder)
        if push:
            m.push_status(heartbeat(err.holder, now))
        return {"busy": err.holder, "heartbeat": push}
    if status is not None:
        m.push_status(status)            # the database is closed: a git push can take its time
    started = apply_reruns(m.gh, lambda job: request_rerun(m, job)) if reruns else 0
    return {"opened": opened, "reruns": started}


# ---- the fire drill (brief stage 8) ------------------------------------------------------------------------------

DRILL_CAUSE = "NSE has not published today's prices yet, so the daily run could not start."


class _DrillGh:
    """A pretend GitHub: remembers the issues the doctor files and shows them back, so the drill needs no network."""

    def __init__(self):
        self.issues, self.calls = [], []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("issue", "create"):
            body = args[args.index("--body") + 1]
            title = args[args.index("--title") + 1]
            self.issues.append({"number": len(self.issues) + 1, "title": title, "body": body,
                                "labels": [{"name": HEAL_LABEL}]})
            return f"https://github.invalid/drill/issues/{len(self.issues)}"
        if args[:2] == ("issue", "list") and RERUN_LABEL in args:       # as if the owner had labelled the issue
            return json.dumps([{**i, "labels": [{"name": RERUN_LABEL}]} for i in self.issues])
        if args[:2] == ("issue", "list"):
            return json.dumps([{"number": i["number"], "title": i["title"]} for i in self.issues])
        return ""


class _DrillMachine:
    """Just enough of a Machine for the doctor's rerun request and the tick: a clock, a root and the scratch store."""

    def __init__(self, root: Path, db_path: Path, now: datetime):
        self.root, self.db_path, self._now, self.ticks = root, db_path, now, 0
        self.start_tick = self._start

    def _start(self):
        self.ticks += 1

    def clock(self):
        return self._now

    @contextmanager
    def db(self, job, wait_s=0):
        db = store.open(self.db_path, job=job)
        try:
            yield db
        finally:
            db.close()


def drill(root: Path | str, live_db: Path | str | None = None, scratch: Path | str | None = None,
          now: datetime | None = None) -> list[dict]:
    """Plant a fault in a scratch store (never the live one), then walk the path a real fault takes. Returns one
    {step, ok, detail} per step: the scratch copy, the doctor seeing the fault, the self-heal issue, the plain-English cause
    in it, no second issue on the next pass, the Rerun request file, and the tick taking that file and running the job.
    GitHub is faked; nothing leaves the machine. A step that fails does not stop the ones that do not need it."""
    now = now or datetime.now()
    own = scratch is None
    folder = Path(tempfile.mkdtemp(prefix="sp-drill-")) if own else Path(scratch)
    results: list[dict] = []

    def step(name, ok, detail=""):
        results.append({"step": name, "ok": bool(ok), "detail": detail})
        return bool(ok)

    def guarded(name, fn):
        try:
            return step(name, *fn())
        except Exception as err:  # noqa: BLE001 - a broken step is a failed step, not a crashed drill
            return step(name, False, f"raised {err!r}")

    names = ["fault seen", "issue opened", "plain cause", "no second issue", "rerun file", "tick takes it"]

    def skip_rest(why):
        for name in names:
            step(name, False, why)

    try:
        db_path = folder / "data" / "sp.duckdb"
        if live_db is not None and Path(live_db).resolve() == db_path.resolve():
            step("scratch copy", False, "the scratch store would be the live store; nothing was planted")
            skip_rest("not run")
            return results
        step("scratch copy", True, f"a new store in {folder}, built by the same migrations as the live one")
        gh, machine = _DrillGh(), _DrillMachine(folder, db_path, now)
        db = store.open(db_path, job="drill")
        try:
            db.execute("insert into runs (job, started_at, finished_at, status, notes) values ('daily_ingest', ?, ?, 'failed', ?)",
                       [now - timedelta(hours=1), now - timedelta(minutes=59), json.dumps({"failed": {"nse_prices": DRILL_CAUSE}})])
            db.execute("insert into problems (job, severity, message) values ('daily_ingest', 'error', ?)", [DRILL_CAUSE])
            cfg = {}

            def seen():
                keys = [f["key"] for f in ops.diagnose(db, cfg, now, folder)]
                return "daily_ingest-failed" in keys, f"findings: {keys}"
            guarded("fault seen", seen)

            def opened():
                n = doctor(db, cfg, now, folder, gh)
                creates = [c for c in gh.calls if c[:2] == ("issue", "create")]
                labelled = bool(creates) and creates[0][creates[0].index("--label") + 1] == HEAL_LABEL
                return n == 1 and len(creates) == 1 and labelled, f"{n} issue(s) opened, {len(creates)} create call(s), label {HEAL_LABEL}"
            guarded("issue opened", opened)

            def plain():
                body = gh.issues[0]["body"] if gh.issues else ""
                good = DRILL_CAUSE in body and "job: daily_ingest" in body and "Traceback" not in body
                return good, ("the issue says why, in words, and names the job" if good else
                              f"the issue body does not carry the cause and 'job: daily_ingest': {body[:120]!r}")
            guarded("plain cause", plain)

            def again():
                n = doctor(db, cfg, now, folder, gh)
                return n == 0 and len(gh.issues) == 1, f"{n} more issue(s); {len(gh.issues)} in all"
            guarded("no second issue", again)
        finally:
            db.close()

        def rerun():
            done = apply_reruns(gh, lambda job: request_rerun(machine, job))
            there = "daily" in due.pending_reruns(folder)
            return done == 1 and there and machine.ticks == 1, f"{done} request(s) read; file data/rerun/daily {'exists' if there else 'is missing'}"
        guarded("rerun file", rerun)

        def taken():
            ran = []
            jobs = {"queue": lambda m, n, force: {"status": "ok"},
                    "daily": lambda m, n, force: ran.append(force) or {"status": "ok"}}
            tick.run(machine, jobs=jobs)
            gone = "daily" not in due.pending_reruns(folder)
            return ran == [True] and gone, f"the tick ran daily {'forced' if ran == [True] else 'not as asked'}; the file is {'gone' if gone else 'still there'}"
        guarded("tick takes it", taken)
    finally:
        if own:
            shutil.rmtree(folder, ignore_errors=True)
    return results
