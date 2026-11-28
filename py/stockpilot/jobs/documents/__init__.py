"""The Documents Job: the readers over new Drive files and Gmail attachments, trades written by key.

Runs in the private repo's `documents.yml` (the real documents never reach the public repo). It reads new files
only: `done` holds the (id, version) of every file already handled, kept between runs by the workflow. Each trade
goes to the door as a row keyed by its trade key, so a file read twice writes the same row twice, never two rows.
"""
import json
import sys
from datetime import timedelta
from pathlib import Path

from stockpilot.heartbeat import beat
from stockpilot.io import Door, new_run_id

KIND = "documents"
DATASET = "documents"
ACCOUNT = "primary"


def trade_rows(trades, account: str = ACCOUNT) -> list[dict]:
    """Parsed `Trade`s as door rows. The key is the exchange trade id, else the content key; the row says whose it is."""
    return [{
        "account": account, "source": t.source, "trade_key": t.key, "source_ref": t.source_ref, "kind": t.kind,
        "symbol": t.symbol, "isin": t.isin, "side": t.side, "trade_date": t.trade_date.isoformat(),
        "quantity": float(t.quantity), "price": None if t.price is None else float(t.price),
    } for t in trades if t.status == "confirmed" and t.side in ("buy", "sell", "vest", "credit", "debit")]


def read_new(bridge, pan: str, done: set, since: str | None = None, limit: int | None = None):
    """Run the readers over files not in `done`; returns the feed result (trades, failures, handled documents)."""
    from stockpilot.trades import feed
    return feed.fetch(bridge, pan, since, done=done, limit=limit)


def run(door: Door, bridge, pan: str, done: set, limit: int | None = None) -> tuple[str, set]:
    """Start, read new files, write rows by key, finish, beat. Returns the run id and the updated `done` set."""
    run_id = new_run_id(KIND)
    door.job_begin(KIND, run_id)
    try:
        result = read_new(bridge, pan, done, limit=limit)
        rows = trade_rows(result.trades)
        if rows:
            door.write_rows(DATASET, run_id, rows)
        note = (f"Read {len(result.handled)} new files: {len(rows)} trades, {len(result.failed)} could not be read"
                + (", more waiting" if result.more else ""))
    except Exception as err:
        door.job_end(run_id, ok=False, error=str(err))
        beat(door, "job.documents", ok=False, error=str(err), every=timedelta(days=1))
        raise
    # Files that failed stay out of `done`, so the next run reads them again.
    done = done | {(h["id"], h["version"]) for h in result.handled}
    door.job_end(run_id, ok=True, result=note)
    beat(door, "job.documents", ok=True, every=timedelta(days=1))
    return run_id, done


def load_done(path: Path) -> set:
    return {tuple(x) for x in json.loads(path.read_text())} if path.exists() else set()


def save_done(path: Path, done: set) -> None:
    path.write_text(json.dumps(sorted(done)))


def main(argv: list[str]) -> int:
    from stockpilot import config
    from stockpilot.jobs.docs import bridge_from
    state = Path(argv[1] if len(argv) > 1 else "documents-done.json")
    bridge, pan = bridge_from(config.load())
    _, done = run(Door.from_env(), bridge, pan, load_done(state))
    save_done(state, done)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
