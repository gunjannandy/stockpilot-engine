"""`sp tick`: the one conductor. The queue first, then at most one due job. systemd never starts a second tick while one
runs, so two jobs cannot collide; a job that did not finish is due again at the next tick, which is the retry."""
from stockpilot import journal, store
from stockpilot.jobs import base_rates, daily, due, nav, ownership, queue, weekly


def _kite(m, now, force: bool = False) -> dict:
    """A Kite read asked for on its own (the owner just logged in): read it, then show it on the page."""
    from stockpilot.jobs import ship
    with m.db("kite") as db:
        out = daily.run_kite(db, m.worker)
        if out["status"] == "ok":
            ship.publish(m, db, today=now.date())
    return out


JOBS = {"queue": queue.run, "daily": daily.run, "gather": daily.gather, "crunch": daily.crunch, "kite": _kite, "nav": nav.run, "weekly": weekly.run,
        "base_rates": base_rates.run, "ownership": ownership.run}


def _run(m, name: str, now, force: bool, report: dict, jobs: dict | None = None) -> None:
    try:
        report[name] = (jobs or JOBS)[name](m, now, force)
    except store.Busy:
        raise
    except Exception as err:  # noqa: BLE001 - one job must not stop the next tick's work
        with m.db("tick") as db:
            journal.problem(db, name, f"{name}: {err!r}", "error", key=f"tick-{name}")
        report[name] = {"status": "failed", "error": repr(err)}


def run(m, jobs: dict | None = None) -> dict:
    """The queue first (a Rerun button pressed now is seen by what follows), then the one job that is due.
    `jobs` replaces the job table; the fire drill passes stand-ins."""
    now = m.clock()
    report: dict = {}
    _run(m, "queue", now, False, report, jobs)
    with m.db("tick") as db:
        journal.prune_resolved(db)
        state = due.read_state(db, now, m.root)
        if due.gave_up(state, now):
            journal.problem(db, "daily_ingest", f"NSE did not publish {now.date()}'s prices.", "error",
                            key=f"nse-late-{now.date()}")
        missing = due.missing_sources(state, now)
        if missing:                  # one grouped row for everything that never arrived today
            journal.problem(db, "gather", f"Not gathered today ({now.date()}): {', '.join(missing)}.",
                            "error" if "nse_prices" in missing else "warning", key=f"gather-missing-{now.date()}")
    for name in due.due(state, now)[1:]:
        force = name in state.rerun
        if force:
            due.take_rerun(m.root, name)          # asked once: a rerun that fails shows as a failed run, not a loop
        _run(m, name, now, force, report, jobs)
    return report


def exit_code(report: dict) -> int:
    """75 when the day's prices are not out yet (no fault: try again); 2 when a job failed; else 0."""
    statuses = {name: (out or {}).get("status") for name, out in report.items() if isinstance(out, dict)}
    if "failed" in statuses.values():
        return 2
    return 75 if "waiting" in (statuses.get("daily"), statuses.get("gather")) else 0
