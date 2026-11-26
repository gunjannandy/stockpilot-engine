"""QUEUE (#114): the page's buttons as D1 jobs. One handler per kind, each doing what the old KV queue's handler did
(`vmqueue.HANDLERS`), so the rules live in one place. Runs on the VM in the one-minute check; the private store is opened
only when a button job arrives, and the idle path imports none of this.

Not here: `feedback` (the page posts to `/api/v2/feedback`), `feedback_decide` (`ask_decide`), `ask_analyst` (the `analyse` job).
No broker code is reached from this module."""
import json
from pathlib import Path

from stockpilot.jobrun import JobFailed

KINDS_FILE = Path(__file__).resolve().parents[3] / "schemas" / "queue-kinds.json"
MOVED = ("feedback", "feedback_decide", "ask_analyst")
BUTTON_KINDS = tuple(k for k in json.loads(KINDS_FILE.read_text())["kinds"] if k not in MOVED)
FAILED_BN = "এটি করা গেল না। আবার চেষ্টা করুন।"


def handler(kind: str, open_db, close=lambda db: None, *, build_pack=None, sync_docs=None, rerun=None):
    """A job handler for one button kind. `open_db()` gives the store; the three optional pieces are what the heavier
    kinds need from the machine (tests pass fakes, `minute._handlers` passes the real ones)."""
    def run(ctx):
        from stockpilot import vmqueue
        fn = vmqueue.HANDLERS[kind]
        args = (ctx.payload, ctx.job.get("asked_by", ""))
        if kind in vmqueue.NEEDS_CONTEXT:
            args += (vmqueue.Context(build_pack=build_pack, sync_docs=sync_docs, rerun=rerun),)
        db = open_db()
        try:
            return fn(db, *args)
        except ValueError as err:                     # the handler's own words, already plain
            raise JobFailed(str(err), FAILED_BN) from err
        finally:
            close(db)
    return run


def handlers(open_db, close=lambda db: None, **machine) -> dict:
    return {k: handler(k, open_db, close, **machine) for k in BUTTON_KINDS}
