"""What is due. `due(state, now)` is pure: `state` is read from `runs`, the calendar and the rerun folder by
`read_state`. The queue runs on every tick, then at most one job, so two jobs never meet."""
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

GATHER_FROM_HOUR = 16         # each source is fetched on its own clock from here; only the missing ones are retried
CRUNCH_EARLY_HOUR = 19        # from here the crunch starts as soon as the required sources are in
CRUNCH_FROM_HOUR = 22         # the fixed crunch time: screen, calls and ship on whatever has arrived
INGEST_UNTIL_HOUR = 23        # a source still missing then is one problem and no more tries
NAV_FROM = (23, 30)
WEEKLY_FROM_HOUR = 10
BASE_RATES_FROM_HOUR = 3
CRUNCH_MAX = 3                # decide twice, plus one stale-day crunch
DECIDE_MAX = 2                # the runner step at most twice an evening: one try and one retry
NAV_MAX = 2
KITE_MAX = 3                  # a failing Kite read is tried at most three times an evening (owners' word, issue #5)
WEEKLY_MAX = 2
RERUN_DIR = Path("data") / "rerun"
# The sources gather fetches, in order. The first twelve are daily_ingest's steps; kite and docs follow.
GATHER_SOURCES = ("nse_prices", "bse_prices", "indices", "surveillance", "announcements", "usdinr", "corporate_actions",
                  "delivery", "deals", "events", "flows", "filings", "kite", "docs")
REQUIRED_SOURCES = frozenset({"nse_prices", "indices"})      # the crunch needs these to run before 22:00
OWNERSHIP_HOURS = (9, 16)     # working hours only: the job is done before the 16:00 gather
OWNERSHIP_MAX = 2
RERUNNABLE = ("daily", "nav", "weekly", "kite", "ownership")


@dataclass(frozen=True)
class State:
    trading_day: bool = True                 # today, by the exchange calendar
    ingest: str | None = None                # status of today's latest daily_ingest run
    gathered: frozenset = field(default_factory=frozenset)   # sources whose data for today is in
    stale_crunch: bool = False               # a crunch today ran on an older day because NSE's prices were not out
    crunch_runs: int = 0
    decide_done: bool = False                # an ok or partial daily_decide run today
    decide_runs: int = 0                     # daily_decide runs started today, whatever their end
    nav_done: bool = False
    nav_runs: int = 0
    weekly_done: bool = False                # the weekly analysis ended ok or partial today
    weekly_runs: int = 0                     # weekly analysis runs that failed today
    base_rates_done: bool = False
    ownership_done: bool = False
    ownership_runs: int = 0
    rerun: frozenset = field(default_factory=frozenset)


def _first_sunday(now: datetime) -> bool:
    return now.weekday() == 6 and now.day <= 7


def _daily(state: State, now: datetime) -> bool:
    return "daily" in state.rerun               # `sp daily` by hand and the Rerun button: gather and crunch in one go


def _gather(state: State, now: datetime) -> bool:
    if not state.trading_day or state.ingest == "holiday":
        return False
    return GATHER_FROM_HOUR <= now.hour < INGEST_UNTIL_HOUR and bool(set(GATHER_SOURCES) - state.gathered)


def _crunch(state: State, now: datetime) -> bool:
    if not state.trading_day or state.ingest == "holiday" or state.decide_done:
        return False
    if state.decide_runs >= DECIDE_MAX or state.crunch_runs >= CRUNCH_MAX:
        return False
    if state.stale_crunch and "nse_prices" not in state.gathered:
        return False                            # already shipped on the old day; wait for NSE rather than repeat it
    if now.hour >= CRUNCH_FROM_HOUR:
        return True
    return now.hour >= CRUNCH_EARLY_HOUR and REQUIRED_SOURCES <= state.gathered


def _nav(state: State, now: datetime) -> bool:
    if "nav" in state.rerun:
        return True
    return (now.hour, now.minute) >= NAV_FROM and not state.nav_done and state.nav_runs < NAV_MAX


def _weekly(state: State, now: datetime) -> bool:
    if "weekly" in state.rerun:
        return True
    return (now.weekday() == 5 and now.hour >= WEEKLY_FROM_HOUR and not state.weekly_done
            and state.weekly_runs < WEEKLY_MAX)


def _base_rates(state: State, now: datetime) -> bool:
    return _first_sunday(now) and now.hour >= BASE_RATES_FROM_HOUR and not state.base_rates_done


def _ownership(state: State, now: datetime) -> bool:
    if "ownership" in state.rerun:
        return True
    return (state.trading_day and OWNERSHIP_HOURS[0] <= now.hour < OWNERSHIP_HOURS[1]
            and not state.ownership_done and state.ownership_runs < OWNERSHIP_MAX)


def due(state: State, now: datetime) -> list[str]:
    """['queue'] plus at most one job, the first that is due in this order."""
    for name, rule in (("daily", _daily), ("crunch", _crunch), ("gather", _gather), ("kite", lambda s, n: "kite" in s.rerun), ("nav", _nav),
                       ("weekly", _weekly), ("base_rates", _base_rates), ("ownership", _ownership)):
        if rule(state, now):
            return ["queue", name]
    return ["queue"]


def gave_up(state: State, now: datetime) -> bool:
    """From 23:00 on a trading day with NSE's prices not gathered: NSE did not publish today's prices."""
    return (state.trading_day and now.hour >= INGEST_UNTIL_HOUR and state.ingest != "holiday"
            and "nse_prices" not in state.gathered)


def missing_sources(state: State, now: datetime) -> list[str]:
    """From 23:00 on a trading day: the sources never gathered today, in gather order (one grouped problem)."""
    if not state.trading_day or state.ingest == "holiday" or now.hour < INGEST_UNTIL_HOUR:
        return []
    return [s for s in GATHER_SOURCES if s not in state.gathered]


# ---- reading the state -----------------------------------------------------------------------------

def ask_rerun(root: Path | str, job: str) -> None:
    """A file, not a row: the doctor and the dashboard ask without needing the database."""
    folder = Path(root) / RERUN_DIR
    folder.mkdir(parents=True, exist_ok=True)
    (folder / job).write_text(datetime.now().isoformat(timespec="seconds"))


def pending_reruns(root: Path | str) -> frozenset:
    folder = Path(root) / RERUN_DIR
    return frozenset(p.name for p in folder.iterdir() if p.name in RERUNNABLE) if folder.is_dir() else frozenset()


def take_rerun(root: Path | str, job: str) -> None:
    (Path(root) / RERUN_DIR / job).unlink(missing_ok=True)


def read_state(db, now: datetime, root: Path | str) -> State:
    from stockpilot.sources import exchange
    today = now.date()

    def runs(job, *statuses):
        q = "select count(*) from runs where job = ? and cast(started_at as date) = ?"
        if statuses:
            q += f" and status in ({', '.join('?' * len(statuses))})"
        return db.execute(q, [job, today, *statuses]).fetchone()[0]

    last = db.execute("select status from runs where job = 'daily_ingest' and cast(started_at as date) = ? "
                      "order by started_at desc, id desc limit 1", [today]).fetchone()
    ingest = last[0] if last else None
    if ingest in ("failed", "waiting") and runs("daily_ingest", "ok", "partial"):
        ingest = "ok"               # a rerun that failed after an ingest that had worked: the prices are in
    gathered = frozenset(period.split(":", 1)[1] for period, in db.execute(
        "select period from fetch_log where source = 'gathered' and period like ?", [f"{today}:%"]).fetchall())
    stale = db.execute("select count(*) from runs where job = 'crunch' and cast(started_at as date) = ? "
                       "and status in ('ok', 'partial') and notes like '%\"stale\": true%'", [today]).fetchone()[0]
    month_start = date(today.year, today.month, 1)
    base_done = db.execute("select count(*) from runs where job = 'base_rates' and started_at >= ? "
                           "and status != 'running'", [month_start]).fetchone()[0]
    return State(trading_day=exchange.is_trading_day(db, today), ingest=ingest, gathered=gathered,
                 stale_crunch=bool(stale), crunch_runs=runs("crunch"),
                 decide_done=bool(runs("daily_decide", "ok", "partial")), decide_runs=runs("daily_decide"),
                 nav_done=bool(runs("nav", "ok", "partial")), nav_runs=runs("nav"),
                 weekly_done=bool(runs("weekly", "ok", "partial")), weekly_runs=runs("weekly", "failed"),
                 base_rates_done=bool(base_done),
                 ownership_done=bool(runs("ownership", "ok", "partial")), ownership_runs=runs("ownership"), rerun=pending_reruns(root))
