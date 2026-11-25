"""The gaps ledger: every empty or partial number records why. The father's screens hide missing data; Health and the
weekly note list it here. One row per (area, subject); recording again refreshes it, resolving closes it."""

REASONS = {
    "not_collected": "Not collected yet",
    "parse_failed": "Could not be read",
    "source_down": "Source is down",
    "quota": "Daily limit reached",
    "waiting_on_owner": "Waiting on the owner",
}


def record(db, area: str, subject: str, reason: str, detail: str = "") -> None:
    if reason not in REASONS:
        raise ValueError(f"unknown gap reason {reason!r}; use one of {sorted(REASONS)}")
    db.execute("insert into gaps (area, subject, reason, detail) values (?, ?, ?, ?) "
               "on conflict (area, subject) do update set reason = excluded.reason, detail = excluded.detail, "
               "last_seen = now(), resolved_at = null", [area, subject, reason, detail])


def resolve(db, area: str, subject: str) -> None:
    db.execute("update gaps set resolved_at = current_timestamp where area = ? and subject = ? and resolved_at is null",
               [area, subject])


def open_gaps(db) -> list[dict]:
    cols = ["area", "subject", "reason", "detail", "first_seen", "last_seen"]
    rows = db.execute(f"select {','.join(cols)} from gaps where resolved_at is null order by area, subject").fetchall()
    return [dict(zip(cols, r)) | {"reason_text": REASONS[r[2]]} for r in rows]


def summary(db) -> dict:
    return dict(db.execute("select reason, count(*) from gaps where resolved_at is null group by reason order by reason").fetchall())


def weekly_note(db, show: int = 8) -> str:
    """A plain-words note for the weekly report; empty when nothing is open."""
    rows = open_gaps(db)
    if not rows:
        return ""
    head = f"{len(rows)} gap{'s' if len(rows) != 1 else ''} in our data: " + ", ".join(
        f"{n} {REASONS[r].lower()}" for r, n in summary(db).items()) + "."
    names = ", ".join(f"{g['subject']} ({g['area']})" for g in rows[:show])
    return f"{head} First: {names}" + (f" and {len(rows) - show} more." if len(rows) > show else ".")
