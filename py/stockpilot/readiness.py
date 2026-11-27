"""Can tonight's brief be trusted? `check` lists what is missing; the list goes at the top of the brief and into the run
notes. Missing prices or base rates stop buy calls (`block_buys`); everything else is a gap the owners can see.
A table that does not exist yet (another lane's source) counts as no data, never as an error."""
from datetime import date, timedelta

FUNDAMENTALS_MAX_AGE_DAYS = 10      # the newest snapshot may be this old
FUNDAMENTALS_MAX_AHEAD_DAYS = 7     # and a snapshot up to this much newer than the day still counts (as in the screen)
RESULTS_REACH_DAYS = 30             # results dates should reach at least this far ahead
ANNOUNCEMENTS_WINDOW_DAYS = 4       # covers a weekend and a holiday


def has_table(db, name: str) -> bool:
    return bool(db.execute("select count(*) from information_schema.tables where table_schema = 'main' "
                           "and table_name = ?", [name]).fetchone()[0])


def _count(db, table: str, where: str, params: list) -> int:
    if not has_table(db, table):
        return 0
    return db.execute(f"select count(*) from {table} where {where}", params).fetchone()[0]


def check(db, day: date) -> dict:
    gaps, block = [], False
    if not _count(db, "prices", "date = ? and exchange = 'NSE'", [day]):
        gaps.append(f"No prices loaded for {day}, so no buy calls tonight.")
        block = True
    newest = db.execute("select max(as_of) from fundamentals where as_of <= ?",
                        [day + timedelta(days=FUNDAMENTALS_MAX_AHEAD_DAYS)]).fetchone()[0]
    if newest is None or newest < day - timedelta(days=FUNDAMENTALS_MAX_AGE_DAYS):
        gaps.append("Fundamentals are over 10 days old" + ("." if newest is None else f" (latest is {newest})."))
    if not _count(db, "announcements", "announced_at >= ? and announced_at < ?",
                  [day - timedelta(days=ANNOUNCEMENTS_WINDOW_DAYS), day + timedelta(days=1)]):
        gaps.append("No NSE announcements fetched in the last 4 days.")
    fetched_today = _count(db, "headlines", "fetched_on = ?", [day]) or _count(
        db, "fetch_log", "source like 'headlines:%' and period = ?", [day.isoformat()])   # a stock with no news is still fetched
    if not fetched_today:
        gaps.append("No news headlines fetched today.")
    if has_table(db, "results_calendar"):
        last = db.execute("select max(date) from results_calendar where date >= ?", [day]).fetchone()[0]
        if last is None:
            gaps.append("Results dates: none are known, so a stock with results coming is not flagged.")
        elif last < day + timedelta(days=RESULTS_REACH_DAYS):
            gaps.append(f"Results dates are known only to {last}, so a later results date is not flagged yet.")
    if not _count(db, "lots", "quantity - closed_quantity > 1e-9", []):
        gaps.append("Holdings are not known (no lots on file), so there are no sell or trim calls.")
    if not _count(db, "base_rates", "horizon_days = 91", []):
        gaps.append("No base rates are stored, so no buy calls tonight.")
        block = True
    return {"gaps": gaps, "block_buys": block}
