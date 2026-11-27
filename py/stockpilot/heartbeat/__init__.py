"""The Python heartbeat library: every part reports its running version, success or error, and when
the next beat is due. A beat that fails to send must not hide the Job's own outcome."""

import os
from datetime import datetime, timedelta

from stockpilot.io import Door

VERSION = os.environ.get("STOCKPILOT_VERSION", "dev")


def beat(door: Door, part: str, *, ok: bool, error: str | None = None, every: timedelta | None = None, now: datetime | None = None) -> bool:
    """Send one beat. Returns False (never raises) when the beat itself could not be sent."""
    from stockpilot.io.clock import ist_now

    due = (now or ist_now()) + every if every else None
    try:
        door.heartbeat(part, VERSION, ok, error, due)
    except Exception:  # noqa: BLE001 (a lost beat shows as overdue on health; the Job's result stands)
        return False
    return True
