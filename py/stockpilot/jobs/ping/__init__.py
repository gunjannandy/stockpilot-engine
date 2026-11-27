"""The Ping Job: writes one row through the door so a press (or a schedule) can read it back."""

import sys
from datetime import timedelta

from stockpilot.heartbeat import beat
from stockpilot.io import Door, new_run_id
from stockpilot.io.clock import ist_now, ist_text

KIND = "ping"
DATASET = "ping"


def run(door: Door) -> str:
    """Start, write one row, finish, beat. Returns the run id; a failure finishes the run failed and re-raises."""
    run_id = new_run_id(KIND)
    door.job_start(KIND, run_id)
    try:
        now = ist_now()
        row = {"id": f"{run_id}-1", "at": ist_text(now), "source": "job"}
        door.write_rows(DATASET, run_id, [row])
    except Exception as err:
        door.job_finish(run_id, ok=False, error=str(err))
        beat(door, "job.ping", ok=False, error=str(err), every=timedelta(days=1))
        raise
    door.job_finish(run_id, ok=True, result="Wrote 1 ping")
    beat(door, "job.ping", ok=True, every=timedelta(days=1))
    return run_id


if __name__ == "__main__":
    print(run(Door.from_env()))
    sys.exit(0)
