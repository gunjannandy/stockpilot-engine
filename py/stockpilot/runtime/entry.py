"""The one entry point every Job runs through (`python -m stockpilot.runtime <kind> ...`).

begin (the Worker refuses a duplicate, a held lock or a paused kind) -> handler -> publish -> end, with
progress lines throughout. A handler gets a `JobContext`; it raises to fail, and the Job ends `failed`,
the Worker schedules the next try with backoff, and the exception goes on to the caller.
"""
import argparse
import importlib
import os
import sys
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date
from typing import TextIO

from stockpilot.heartbeat import beat
from stockpilot.io import Door
from stockpilot.io.clock import ist_now, ist_text

from .client import JobClient, JobRefused
from .daterange import DateRange, parse_range
from .idempotent import stable_rows
from .progress import Progress


@dataclass
class JobContext:
    kind: str
    subject: str
    run_id: str
    range: DateRange
    client: JobClient
    progress: Progress
    expected_seconds: int | None = None
    published: list[str] = field(default_factory=list)

    def publish(self, dataset: str, rows: list[dict], *, source: str, as_of: str | None = None, **finish) -> dict:
        """Send the rows (de-duplicated, in id order) and finish the dataset's run; the pointer moves when its checks pass."""
        batch = stable_rows(rows)
        fetched = ist_text(ist_now())
        for i in range(0, max(len(batch), 1), 1000):
            self.client.publish_rows(dataset, self.run_id, batch[i:i + 1000], source=source, fetched_at=fetched,
                                     as_of=as_of or str(self.range.end))
        out = self.client.publish_finish(dataset, self.run_id, **finish)
        self.published.append(dataset)
        self.progress.line(f"{dataset}: {len(batch)} rows, {'published' if out.get('published') else 'not published'}",
                           "ok" if out.get("published") else "fail")
        return out


Handler = Callable[[JobContext], str | None]


def run_job(kind: str, handler: Handler, *, door: Door, subject: str = "all", day: str | None = None,
            start: str | None = None, end: str | None = None, rerun: bool = False, out: TextIO | None = None,
            run_id: str | None = None) -> str:
    """Run one Job end to end. Returns the run id; raises `JobRefused` (nothing ran) or the handler's own error."""
    client = JobClient(door)
    today = ist_now().date()
    rng = parse_range(start, end, date.fromisoformat(day) if day else today)
    run_id = run_id or f"{kind}-{today:%Y%m%d}-{uuid.uuid4().hex[:8]}"
    started = client.begin(kind, run_id, subject=subject, day=day, start=str(rng.start), end=str(rng.end), rerun=rerun)
    progress = Progress(run_id, out) if out is not None else Progress(run_id)
    progress.line(f"{kind} {subject} started for {rng}"
                  + (f", usually about {started['expected_seconds']} seconds" if started.get("expected_seconds") else ""))
    ctx = JobContext(kind, subject, run_id, rng, client, progress, started.get("expected_seconds"))
    try:
        result = handler(ctx) or "done"
    except Exception as err:
        progress.line(f"failed: {err}", "fail")
        client.end(run_id, ok=False, error=str(err)[:500])
        beat(door, f"job.{kind}", ok=False, error=str(err)[:300])
        raise
    progress.line(result, "ok")
    client.end(run_id, ok=True, result=result[:500])
    beat(door, f"job.{kind}", ok=True)
    return run_id


def load_handler(kind: str) -> Handler:
    """`stockpilot.jobs.<kind>` must export `run(ctx)`."""
    module = importlib.import_module(f"stockpilot.jobs.{kind}")
    return module.run


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m stockpilot.runtime")
    ap.add_argument("kind")
    ap.add_argument("--subject", default="all")
    ap.add_argument("--day")
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--rerun", action="store_true")
    a = ap.parse_args(argv)
    door = Door.from_env()
    try:
        run_job(a.kind, load_handler(a.kind), door=door, subject=a.subject, day=a.day or os.environ.get("JOB_DAY"),
                start=a.start, end=a.end, rerun=a.rerun)
    except JobRefused as err:
        print(f"refused: {err}", file=sys.stderr)
        return 0  # a duplicate or a held lock is the runtime doing its job, not a failure
    return 0
