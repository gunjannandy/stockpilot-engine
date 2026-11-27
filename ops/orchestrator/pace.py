"""Quota pacing (decisions §9). Pure functions, no model call, no network.

Inputs per account: the `rate_limit_info` readings its sessions report
({window: five_hour|seven_day, status: allowed|allowed_warning|rejected, resetsAt}), its role, the mode,
and its weekly reset. Output: whether this account may start work now.

Rules
- Burst: start while allowed. A five-hour warning stops every account. A seven-day warning stops the driver
  only, so the owner can always chat; the spare account may spend its weekly room.
- Rejected waits for resetsAt, then counts as allowed again.
- Steady: at most one start per wake, and no start while any warning shows. Weekly warnings are ignored in the
  last 12 hours before the weekly reset (the reserve is released) and in the account's last week before it lapses.
- Hotfixes ignore warnings but never start while the account is refused (`refused`).
"""
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=5, minutes=30))
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
UI_BUDGET_LIMIT = 0.8
RESERVE_HOURS = 12
LAPSE_WEEK_DAYS = 7


def parse_time(value):
    """ISO string, epoch seconds or None -> aware datetime or None."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, tz=timezone.utc)
    dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def latest(readings):
    """Each window's most recent reading; the list is oldest first."""
    by_window = {}
    for r in readings:
        by_window[r["window"]] = r
    return list(by_window.values())


def hours_to_weekly_reset(now, weekly_reset):
    """'Fri 22:30 IST' -> hours from now to the next such moment."""
    day, clock, _tz = weekly_reset.split()
    hh, mm = (int(x) for x in clock.split(":"))
    local = now.astimezone(IST)
    target = local.replace(hour=hh, minute=mm, second=0, microsecond=0)
    target += timedelta(days=(DAYS.index(day.lower()[:3]) - local.weekday()) % 7)
    if target <= local:
        target += timedelta(days=7)
    return (target - local).total_seconds() / 3600


def effective(reading, now):
    """A warning or rejection whose window has already reset no longer applies."""
    resets = parse_time(reading.get("resetsAt"))
    if reading["status"] != "allowed" and resets is not None and resets <= now:
        return "allowed"
    return reading["status"]


def account_state(readings, *, role, mode, now, weekly_reset, lapses=None):
    now = parse_time(now)
    refused = False
    wait_until = None
    five_warn = seven_warn = seven_rejected = False
    for r in latest(readings):
        status = effective(r, now)
        if status == "rejected":
            refused = True
            wait_until = r.get("resetsAt")
            seven_rejected = seven_rejected or r["window"] == "seven_day"
        elif status == "allowed_warning":
            if r["window"] == "seven_day":
                seven_warn = True
            else:
                five_warn = True
    reserve_released = hours_to_weekly_reset(now, weekly_reset) <= RESERVE_HOURS
    if lapses:
        reserve_released = reserve_released or (parse_time(lapses) - now) <= timedelta(days=LAPSE_WEEK_DAYS)
    seven_warn_counts = seven_warn and not reserve_released
    if mode == "steady":
        warned = five_warn or seven_warn_counts
    else:
        warned = five_warn or (seven_warn_counts and role == "driver")
    can_start = not refused and not warned
    reason = "refused until reset" if refused else "warning" if warned else "allowed"
    return {"can_start": can_start, "refused": refused, "wait_until": wait_until, "reason": reason,
            "max_starts": 1 if mode == "steady" else None}


def ui_budget_ok(cloudflare):
    """No UI ticket starts above 80% of build minutes, D1 writes, requests or Actions concurrency."""
    keys = ("build_minutes", "d1_writes", "requests", "actions_concurrency")
    return all(cloudflare.get(k, 0) <= UI_BUDGET_LIMIT for k in keys)
