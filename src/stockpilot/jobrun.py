"""The one entry point for every v2 job kind (ticket T14, contract `schemas/live-contract.json`).

`JobRunner.enqueue` checks the kind and payload against the contract's `job_kinds`; `run` moves the job queued -> running
-> done or failed, and hands the handler a `ctx` whose `progress()` appends numbered lines. A sink stores the rows
(`MemorySink` in tests, `SqliteSink` for D1's tables) and refuses a bad row at write time: a gap in `seq`, a time that is
not IST, an unknown state, a job that goes backwards. Secrets are scrubbed from every line. The model is whatever the
caller passes; tests pass a fake, and a job that needs one with none given fails in plain words and spends nothing."""
import json
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from stockpilot.jobs.vmjobs import scrub

IST = timezone(timedelta(hours=5, minutes=30))
CONTRACT = json.loads((Path(__file__).resolve().parents[2] / "schemas" / "live-contract.json").read_text())
KINDS = {k: v["payload"] for k, v in CONTRACT["job_kinds"].items()}
STATUSES = ("queued", "running", "done", "failed")
LINE_STATES = ("info", "ok", "fail")
ASKERS = ("owner", "father", "system")
TIME_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+05:30$")
GENERIC = "Something went wrong and the owner has been told. Try again later."
GENERIC_BN = "কিছু একটা গোলমাল হয়েছে। পরে আবার চেষ্টা করুন।"
NO_MODEL = "No model is available for this job. Try again later."


class BadJob(ValueError):
    """The request names an unknown kind, a wrong payload or an unknown asker."""


class TrustError(ValueError):
    """A row the contract forbids; refused before it is stored."""


class JobFailed(Exception):
    """A handler's own failure, already in plain words."""
    def __init__(self, text: str, text_bn: str | None = None):
        super().__init__(text)
        self.text, self.text_bn = text, text_bn


def check_shape(value, shape, path="$") -> list[str]:
    """Problems of `value` against the contract's shape language (object, list, str int num bool json date time enum, `?`)."""
    if isinstance(shape, dict):
        if not isinstance(value, dict):
            return [f"{path}: expected object"]
        bad = []
        for key, sub in shape.items():
            name = key.rstrip("?")
            if name not in value:
                if not key.endswith("?"):
                    bad.append(f"{path}.{name}: missing")
                continue
            bad += check_shape(value[name], sub, f"{path}.{name}")
        known = {k.rstrip("?") for k in shape}
        return bad + [f"{path}.{k}: not in contract" for k in value if k not in known]
    if isinstance(shape, list):
        return [f"{path}: expected list"] if not isinstance(value, list) else [p for i, v in enumerate(value) for p in check_shape(v, shape[0], f"{path}[{i}]")]
    base = shape.rstrip("?")
    if value is None:
        return [] if shape.endswith("?") else [f"{path}: null not allowed"]
    if base == "json":
        return []
    if base.startswith("enum("):
        return [] if value in base[5:-1].split("|") else [f"{path}: {value!r} not one of {base}"]
    ok = {"str": isinstance(value, str), "int": isinstance(value, int) and not isinstance(value, bool),
          "num": isinstance(value, (int, float)) and not isinstance(value, bool), "bool": isinstance(value, bool),
          "time": isinstance(value, str) and bool(TIME_RE.match(value)),
          "date": isinstance(value, str) and bool(re.match(r"^\d{4}-\d{2}-\d{2}$", value))}.get(base, False)
    return [] if ok else [f"{path}: expected {base}"]


_JOB_SHAPE = CONTRACT["tables"]["jobs"]["columns"]
_LINE_SHAPE = CONTRACT["progress_line"]["shape"]


class MemorySink:
    """Rows in memory, with the write-time checks every sink shares."""

    def __init__(self):
        self.jobs: dict[str, dict] = {}
        self.lines: dict[str, list[dict]] = {}
        self.history: dict[str, list[str]] = {}

    # --- the checks -------------------------------------------------------------------------------------
    def create_job(self, row: dict) -> None:
        problems = check_shape(row, _JOB_SHAPE)
        if problems:
            raise TrustError("job row: " + "; ".join(problems))
        if row["status"] != "queued" or row["id"] in self.jobs:
            raise TrustError("job row: a new job is queued and has a new id (status)")
        self.jobs[row["id"]] = dict(row)
        self.lines[row["id"]] = []
        self.history[row["id"]] = ["queued"]

    def update_job(self, job_id: str, **fields) -> None:
        job = self.jobs.get(job_id)
        if job is None:
            raise TrustError(f"no job {job_id}")
        new = {**job, **fields}
        problems = check_shape(new, _JOB_SHAPE)
        if problems:
            raise TrustError("job row: " + "; ".join(problems))
        old_status, status = job["status"], new["status"]
        if status != old_status and (STATUSES.index(status) != STATUSES.index(old_status) + 1
                                     and not (old_status == "running" and status in ("done", "failed"))
                                     and not (old_status == "queued" and status == "failed")):
            raise TrustError(f"status cannot go {old_status} -> {status}")
        if old_status in ("done", "failed") and new != job:
            raise TrustError(f"status: a {old_status} job stays finished")
        if status == "done" and not new["result"]:
            raise TrustError("status done needs a result")
        if status == "failed" and not new["error"]:
            raise TrustError("status failed needs an error in words")
        self._store_job(job_id, new)
        if status != old_status:
            self.history[job_id].append(status)

    def append_line(self, row: dict) -> None:
        problems = check_shape(row, _LINE_SHAPE)
        if problems:
            raise TrustError("line: " + "; ".join(problems))
        if row["job_id"] not in self.jobs:
            raise TrustError(f"line for unknown job {row['job_id']}")
        if not row["text"].strip():
            raise TrustError("line: text is empty")
        if self.jobs[row["job_id"]]["status"] in ("done", "failed"):
            raise TrustError("line: job already finished (status)")
        if row["seq"] != self._last_seq(row["job_id"]) + 1:
            raise TrustError(f"line: seq must be {self._last_seq(row['job_id']) + 1}, got {row['seq']}")
        self._store_line(row)

    # --- storage ----------------------------------------------------------------------------------------
    def _last_seq(self, job_id): return len(self.lines[job_id])
    def _store_job(self, job_id, row): self.jobs[job_id] = row
    def _store_line(self, row): self.lines[row["job_id"]].append(dict(row))

    def queued(self) -> list[str]:
        return [j["id"] for j in sorted(self.jobs.values(), key=lambda j: (j["created_at"], j["id"])) if j["status"] == "queued"]


class SqliteSink(MemorySink):
    """The same rows in D1's tables (SQLite). The in-memory dicts are the cache the checks read; the database is written too."""

    def __init__(self, db):
        super().__init__()
        self.db = db

    def _store_job(self, job_id, row):
        super()._store_job(job_id, row)
        cols = list(_JOB_SHAPE)
        values = [json.dumps(row[c]) if c == "payload" else row[c] for c in cols]
        self.db.execute(f"insert or replace into jobs ({','.join(cols)}) values ({','.join('?' * len(cols))})", values)
        self.db.commit()

    def create_job(self, row):
        super().create_job(row)          # a new job is stored by _store_job via update path below
        self._store_job(row["id"], self.jobs[row["id"]])

    def _store_line(self, row):
        super()._store_line(row)
        cols = list(_LINE_SHAPE)
        self.db.execute(f"insert into job_lines ({','.join(cols)}) values ({','.join('?' * len(cols))})", [row[c] for c in cols])
        self.db.commit()


class Context:
    """What a handler sees: its payload, a way to say what it is doing, and the model it was given."""

    def __init__(self, runner, job):
        self._runner, self.job, self.payload = runner, job, job["payload"]
        self._model = runner.model

    @property
    def model(self):
        if self._model is None:
            raise JobFailed(NO_MODEL)
        return self._model

    def progress(self, text: str, text_bn: str | None = None, state: str = "info") -> None:
        self._runner.line(self.job["id"], state, text, text_bn)


class JobRunner:
    def __init__(self, sink, model=None, clock=None):
        self.sink, self.model = sink, model
        self.clock = clock or (lambda: datetime.now(IST))
        self.handlers: dict = {}

    def register(self, kind: str, handler) -> None:
        if kind not in KINDS:
            raise BadJob(f"unknown job kind {kind!r}")
        self.handlers[kind] = handler

    def _now(self) -> str:
        return self.clock().astimezone(IST).replace(microsecond=0).isoformat()

    def enqueue(self, kind: str, payload: dict, asked_by: str) -> str:
        if kind not in KINDS:
            raise BadJob(f"unknown job kind {kind!r}")
        if sorted(payload) != sorted(KINDS[kind]):
            raise BadJob(f"payload for {kind} must have exactly {KINDS[kind]}, got {sorted(payload)}")
        if asked_by not in ASKERS:
            raise BadJob(f"asked_by must be one of {ASKERS}")
        job_id = f"job_{uuid.uuid4().hex[:12]}"
        self.sink.create_job({"id": job_id, "kind": kind, "payload": payload, "asked_by": asked_by, "status": "queued",
                              "result": None, "error": None, "error_bn": None, "created_at": self._now(),
                              "started_at": None, "finished_at": None})
        return job_id

    def line(self, job_id: str, state: str, text: str, text_bn: str | None = None) -> None:
        self.sink.append_line({"job_id": job_id, "seq": self.sink._last_seq(job_id) + 1, "at": self._now(), "state": state,
                               "text": scrub(text), "text_bn": scrub(text_bn) if text_bn else None})

    def run(self, job_id: str) -> str:
        job = self.sink.jobs[job_id]
        self.sink.update_job(job_id, status="running", started_at=self._now())
        handler = self.handlers.get(job["kind"])
        try:
            if handler is None:
                raise JobFailed("This kind of job is not set up yet.")
            result = handler(Context(self, job))
            result = scrub(str(result or "Done"))
            self.line(job_id, "ok", result)
            self.sink.update_job(job_id, status="done", result=result, finished_at=self._now())
        except Exception as err:  # noqa: BLE001 - every failure becomes plain words on the job
            text, text_bn = (err.text, err.text_bn) if isinstance(err, JobFailed) else (GENERIC, GENERIC_BN)
            text, text_bn = scrub(text), scrub(text_bn) if text_bn else None
            self.line(job_id, "fail", text, text_bn)
            self.sink.update_job(job_id, status="failed", error=text, error_bn=text_bn, finished_at=self._now())
        return job_id

    def run_next(self) -> str | None:
        queued = self.sink.queued()
        return self.run(queued[0]) if queued else None


def legacy(fn, machine, now, say: str):
    """Put a v1 tick job (`fn(machine, now, force) -> dict`) behind the entry point without rewriting it."""
    def handler(ctx):
        ctx.progress(f"{say} started")
        out = fn(machine, now(), False) or {}
        if out.get("status") == "failed":
            raise JobFailed(f"{say} did not finish. The owner has been told.")
        rows = out.get("rows")
        return f"Done, {rows} rows" if rows is not None else "Done"
    return handler
