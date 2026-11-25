"""The owners' "Not now": hide a stock from one kind of call. SNOOZE hides it for 30 days; DISMISS (the cross) hides it
until undone. The older week / month / good words still work: week and month snooze, good dismisses. No reason asked.
Undo is a second request. The forecaster never sees these; selection applies them (`forecast.active_not_now`)."""
import builtins
import re
from datetime import date, timedelta

SCOPES = ("buy", "sell", "any")
DURATIONS = {"snooze": 30, "dismiss": None, "week": 7, "month": 30, "good": None}
SNOOZE_DAYS = 30


def set(db, symbol: str, scope: str, for_: str, by: str, day: date) -> int:
    """Set a stock aside; returns its id. The same stock and scope again moves the end date and keeps the id."""
    symbol = str(symbol or "").strip().upper()
    if not re.fullmatch(r"[A-Z0-9&-]{1,20}", symbol):
        raise ValueError(f"'{symbol}' is not a stock symbol.")
    if scope not in SCOPES:
        raise ValueError(f"Scope must be buy, sell or any, not '{scope}'.")
    if for_ not in DURATIONS:
        raise ValueError(f"Choose a week, a month or for good, not '{for_}'.")
    days = DURATIONS[for_]
    until = day + timedelta(days=days) if days else None
    how = "snooze" if days else "dismiss"
    row = db.execute("select id, until from not_now where symbol = ? and scope = ? and undone_at is null "
                     "and (until is null or until >= ?)", [symbol, scope, day]).fetchone()
    if row:
        if row[1] is None and until is not None:
            return row[0]    # a snooze never weakens a dismissal
        db.execute("update not_now set until = ?, set_by = ?, how = ? where id = ?", [until, by, how, row[0]])
        return row[0]
    return db.execute("insert into not_now (symbol, scope, until, set_by, how) values (?, ?, ?, ?, ?) returning id",
                      [symbol, scope, until, by, how]).fetchone()[0]


def dismissed(db) -> list[dict]:
    """Every dismissal ever made, undone ones included, oldest first."""
    rows = db.execute("select id, symbol, scope, set_by, set_at, undone_at from not_now where how = 'dismiss' order by id").fetchall()
    return [{"id": i, "symbol": s, "scope": sc, "set_by": by, "set_at": at, "undone_at": un} for i, s, sc, by, at, un in rows]


def undo(db, not_now_id) -> None:
    if isinstance(not_now_id, bool) or not isinstance(not_now_id, int):
        raise ValueError("Undo needs the id of the Not now.")
    row = db.execute("select undone_at from not_now where id = ?", [not_now_id]).fetchone()
    if row is None:
        raise ValueError("That Not now does not exist.")
    if row[0] is not None:
        raise ValueError("That Not now was already undone.")
    db.execute("update not_now set undone_at = current_timestamp where id = ?", [not_now_id])


def active(db, day: date) -> "builtins.set[tuple[str, str]]":
    """{(symbol, scope)} in force on `day`; a week set on the 2nd holds through the 9th."""
    return builtins.set(db.execute("select symbol, scope from not_now where undone_at is null and (until is null or until >= ?)",
                          [day]).fetchall())


def settings_payload(db, day: date, default_budget: float) -> dict:
    """site/settings.json: what the owners have set, for the pages to show and undo. No page reads it yet."""
    from stockpilot import forecast, watchlist   # forecast imports the book package, so import it late
    from stockpilot.book import budget
    rows = db.execute("select n.id, n.symbol, n.scope, n.until, n.set_by, n.how, s.industry from not_now n "
                      "left join stocks s using (symbol) where n.undone_at is null "
                      "and (n.until is null or n.until >= ?) order by n.id", [day]).fetchall()
    return {"as_of": str(day),
            "not_now": [{"id": i, "symbol": s, "scope": sc, "until": str(u) if u else None, "set_by": by,
                         "how": how, "industry": ind} for i, s, sc, u, by, how, ind in rows],
            "budget": {"month": day.strftime("%Y-%m"), "total": budget.for_month(db, day, default_budget),
                       "left": forecast.budget_left(db, day, default_budget)},
            "watchlist_count": len(watchlist.active(db))}
