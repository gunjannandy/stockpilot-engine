"""Scheduled jobs. Each takes its fetchers, so tests run them end to end on saved real files.
A failing source never stops the others: it becomes a problem row, and the run ends 'partial'."""
import traceback
from datetime import date, datetime, timedelta
from pathlib import Path

import duckdb

from stockpilot.book import budget as book_budget
from stockpilot import feedback, forecast, journal
from stockpilot.calls import decide
from stockpilot.sources import exchange, fx, kite, marketdata, news
from stockpilot.analysis import screen
from stockpilot.jobs import docs, due, ship
from stockpilot.sources import deals, delivery, events, filings, flows
from stockpilot.trades import corporate_actions, corporate_actions_feeds


# A source whose count is zero has not published yet: it is not done, and it is not a failure either.
SPECIAL_LOOK_BACK = 10
PUBLISHED = {"nse_prices", "bse_prices", "indices", "delivery", "usdinr"}


def _corporate_actions(db, day: date, fetch_json) -> int:
    """The main-board feed (its count is the step's), then the ETF and SME feeds NSE keeps apart."""
    n = corporate_actions.ingest(db, day, fetch_json)
    corporate_actions_feeds.ingest(db, day, fetch_json)
    return n


def daily_ingest(db: duckdb.DuckDBPyConnection, day: date, fetch, fetch_json, only=None) -> dict:
    """The exchange sources for `day`. `only` limits it to those source names (gather's retry of the missing ones)."""
    run_id = journal.start(db, "daily_ingest")
    counts, failed = {}, {}
    if only is None or "nse_prices" in only:       # the calendar is asked once, with NSE; a retry of the rest does not
        try:
            exchange.refresh_holidays(db, fetch_json)
        except Exception as err:  # an unknown calendar is not fatal: weekends are still skipped
            failed["holidays"] = repr(err)
    if only is None or "nse_prices" in only:
        try:       # a Sunday Budget session or a Muhurat evening is not on the calendar: look for the file once per closed day
            marketdata.ingest_special_sessions(db, day - timedelta(days=SPECIAL_LOOK_BACK), day, fetch)
        except Exception as err:  # noqa: BLE001 - a missing extra session never stops the day's ingest
            journal.problem(db, "daily_ingest", f"special sessions: {err!r}", "warning", key="special_sessions")
    if not exchange.is_trading_day(db, day):
        journal.finish(db, run_id, "holiday", {"day": day})
        return {"status": "holiday", "counts": {}, "failed": failed}
    steps = {
        "nse_prices": lambda: marketdata.ingest_nse_bhavcopy(db, day, fetch),
        "bse_prices": lambda: marketdata.ingest_bse_bhavcopy(db, day, fetch),
        "indices": lambda: marketdata.ingest_index_closes(db, day, fetch),
        "surveillance": lambda: len(exchange.refresh_surveillance(db, day, fetch_json)),
        "announcements": lambda: news.ingest_announcements(db, day, fetch_json),
        "usdinr": lambda: fx.ingest_usdinr(db, day, fetch),
        "corporate_actions": lambda: _corporate_actions(db, day, fetch_json),
        "delivery": lambda: delivery.ingest(db, day, fetch),
        "deals": lambda: deals.ingest(db, day, fetch_json),
        "events": lambda: events.ingest(db, day, fetch_json),
        "flows": lambda: flows.ingest(db, day, fetch_json),
        "filings": lambda: filings.ingest(db, day, fetch_json),
    }
    tracebacks = {}
    for name, step in steps.items():
        if only is not None and name not in only:
            continue
        try:
            counts[name] = step()
        except marketdata.NotPublished:    # not out yet: a zero count, tried again by the next tick, no warning
            counts[name] = 0
        except Exception as err:
            failed[name] = repr(err)
            tracebacks[name] = traceback.format_exc()[-4000:]          # the run notes keep it; the Health tab does not
            journal.problem(db, "daily_ingest", f"{name}: {err!r}", "error" if name == "nse_prices" else "warning", key=name)
    note = None
    if (only is None or "nse_prices" in only) and counts.get("nse_prices", 0) == 0 and "nse_prices" not in failed:
        note = f"NSE has not published {day} yet"      # a trading day by the calendar and no bhavcopy: try again later
    if only is not None and "nse_prices" not in only:
        status = "ok" if not failed else "partial"          # NSE was already in; this tick retried the rest
    elif "nse_prices" in failed:
        status = "failed"
    elif note:
        status = "waiting"
    else:
        status = "ok" if not failed else "partial"
    notes = {"counts": counts, "failed": failed, "tracebacks": tracebacks, **({"note": note} if note else {})}
    journal.finish(db, run_id, status, notes)
    return {"status": status, "counts": counts, "failed": failed, **({"note": note} if note else {})}


def daily_decide(db: duckdb.DuckDBPyConnection, day: date, analyse, runners: list[str], rules: decide.Rules,
                 budget_inr: float, liquidity_floor_cr: float = 1.0, brief_dir=None, fetch=None) -> dict:
    """Screen, dossiers, judge, size and log today's calls (see forecast.run). The model forecasts; code acts."""
    return forecast.run(db, day, analyse, runners, rules, budget_inr, liquidity_floor_cr, brief_dir=brief_dir, fetch=fetch)


# ---- the job: `sp tick` calls run() -------------------------------------------------------------------

def _release(db) -> None:
    getattr(db, "suspend", lambda: None)()


def run_kite(db, worker) -> dict:
    """The Kite read as a tracked run, with the lock let go while the Worker answers. 'Login needed' is a note, not a
    failure: an owner presses Sync now."""
    run_id = journal.start(db, "kite")
    try:
        _release(db)
        summary = kite.store_payload(db, kite.fetch(worker))
        docs.mark_acted(db)
        journal.finish(db, run_id, "ok", summary)
        return {"status": "ok", **summary}
    except kite.LoginNeeded as err:
        journal.finish(db, run_id, "ok", {"login_needed": True, "note": str(err)})
        return {"status": "login_needed", "note": str(err)}
    except Exception as err:  # noqa: BLE001 - yesterday's holdings are still usable
        journal.problem(db, "kite", f"kite sync: {err!r}")
        journal.finish(db, run_id, "failed", {"error": str(err)})
        return {"status": "failed", "error": str(err)}


def _done_today(db, day: date, job: str) -> bool:
    return bool(db.execute("select count(*) from runs where job = ? and cast(started_at as date) = ? "
                           "and status in ('ok', 'partial')", [job, day]).fetchone()[0])


def run_asks(m, db, day: date, rules=None) -> dict:
    """Answer the owners' "Ask the analyst" requests (one runner call per stock, at most five). Never stops the run."""
    from stockpilot import asks
    outside = getattr(db, "releasing", lambda f: f)
    try:
        return asks.run_pending(db, day, outside(m.analyse), m.runners, rules or decide.Rules.from_config(m.cfg),
                                m.cfg.get("universe.liquidity_floor_cr", 1.0))
    except Exception as err:  # noqa: BLE001
        journal.problem(db, "asks", f"Ask step failed: {err!r}", key="asks:step")
        return {"status": "failed", "error": repr(err)}


def run_feedback(m, db, now) -> dict:
    """Evening triage of the owners' feedback, after ship. It never stops the run; when it changed something the page is
    built and deployed again so the owners see the new plan tonight."""
    outside = getattr(db, "releasing", lambda f: f)
    try:
        out = feedback.triage(db, now.date(), outside(m.analyse), m.runners, outside(m.gh))
        if out["changed"]:
            out["published"] = ship.publish(m, db, now.date())
        return out
    except Exception as err:  # noqa: BLE001
        journal.problem(db, "feedback", f"Feedback step failed: {err!r}", key="feedback:step")
        return {"status": "failed", "error": repr(err)}


# ---- gather: each source on its own clock ------------------------------------------------------------

def _gathered(db, day: date) -> set:
    return {p.split(":", 1)[1] for p, in db.execute(
        "select period from fetch_log where source = 'gathered' and period like ?", [f"{day}:%"]).fetchall()}


def _mark(db, day: date, name: str) -> None:
    db.execute("insert or replace into fetch_log values ('gathered', ?)", [f"{day}:{name}"])


def gather(m, now: datetime, force: bool = False) -> dict:
    """One tick of gathering: run only the sources not yet in for today, each on its own (a failing one is a problem row
    and never blocks another), and mark each that arrived. NSE's bhavcopy not being out is 'not done', not a failure.
    `force` (a rerun) fetches everything again."""
    day = now.date()
    report: dict = {}
    with m.db("gather") as db:
        have = set() if force else _gathered(db, day)
        pending = [s for s in due.GATHER_SOURCES if s not in have]
        report["pending"] = []
        if not pending:
            return {"status": "ok", "pending": []}
        exchange_pending = [s for s in pending if s not in ("kite", "docs")]
        out = {"status": "ok", "counts": {}, "failed": {}}
        if exchange_pending:
            out = daily_ingest(db, day, db.releasing(m.fetch), db.releasing(m.fetch_json), only=set(exchange_pending))
            report["ingest"] = out
        if out["status"] == "holiday":
            return {"status": "holiday", "pending": []}
        for name, count in out["counts"].items():
            if not (name in PUBLISHED and not count):
                _mark(db, day, name)
        if "kite" in pending:
            if not m.worker:
                _mark(db, day, "kite")                      # nothing to read: not a gap
            else:
                report["kite"] = run_kite(db, m.worker)
                if report["kite"]["status"] in ("ok", "login_needed"):
                    _mark(db, day, "kite")                  # 'login needed' waits for the owner, not for another try
        if "docs" in pending:
            text, more = docs.sync_safely(m, db, "daily")
            report["docs"] = text
            if not more and not text.startswith("Document sync skipped"):
                _mark(db, day, "docs")
        left = [s for s in due.GATHER_SOURCES if s not in _gathered(db, day)]
        report["pending"] = left
        new = len(left) < len(pending)
        if not exchange_pending:
            pass
        elif not new and not out["failed"] and db.execute(           # a tick that learned nothing leaves no run row of its own
                "select count(*) from runs where job = 'daily_ingest' and cast(started_at as date) = ?", [day]).fetchone()[0] > 1:
            db.execute("delete from runs where id = (select max(id) from runs where job = 'daily_ingest')")
        else:                                                   # an older 'waiting' row says nothing the newest does not
            db.execute("delete from runs where job = 'daily_ingest' and status = 'waiting' and cast(started_at as date) = ? "
                       "and id < (select max(id) from runs where job = 'daily_ingest')", [day])
        if out["status"] == "waiting" or "nse_prices" in left:
            status = "waiting"
        else:
            status = "partial" if out["failed"] or left else "ok"
        return {**report, "status": status, "failed": out["failed"]}


# ---- crunch: screen -> calls -> ship on whatever has arrived ------------------------------------------

def _stale_label(today: date, day: date) -> str:
    return f"Calls are from {day:%a %d %b}; today's prices were not out."


def crunch(m, now: datetime, force: bool = False) -> dict:
    """Screen once, make the calls, ship. With NSE's prices for today missing it works on the latest published trading day,
    never duplicates that day's calls (it only rebuilds and ships, so every number refreshes and the calls stay dated), and
    ends 'partial' with a plain note."""
    cfg, today = m.cfg, now.date()
    floor = cfg.get("universe.liquidity_floor_cr", 1.0)
    report: dict = {}
    with m.db("daily") as db:
        run_id = journal.start(db, "crunch")
        try:
            day, stale = today, False
            if "nse_prices" not in _gathered(db, today) and not force:
                latest = db.execute("select max(date) from prices where exchange = 'NSE' and date < ?", [today]).fetchone()[0]
                if latest is None:
                    journal.finish(db, run_id, "failed", {"error": "no prices at all"})
                    return {"status": "waiting", "note": "No prices have been published yet."}
                day, stale = latest, True
            report["day"] = str(day)
            screen.run(db, day, floor, fresh=True)                # once; the calls, the site and the weekly read this one
            has_calls = bool(db.execute("select count(*) from calls where made_on = ?", [day]).fetchone()[0])
            if stale and has_calls:
                report["decide"] = {"status": "skipped", "note": f"Calls for {day} already exist."}
            else:
                budget = book_budget.for_month(db, day, cfg.get("budget.monthly_default_inr", 100000))
                report["decide"] = daily_decide(db, day, db.releasing(m.analyse), m.runners, decide.Rules.from_config(cfg),
                                                budget, floor, brief_dir=cfg.root / "data" / "briefs", fetch=db.releasing(m.fetch))
            decided = report["decide"]["status"]
            report["status"] = "partial" if stale and decided in ("ok", "skipped") else decided
            if stale:
                report.update(stale=True, calls_from=str(day), note=_stale_label(today, day))
            report["asks"] = run_asks(m, db, day)               # before ship, so tonight's page carries the answers
            report["ship"] = ship.ship(m, db, now)
            report["feedback"] = run_feedback(m, db, now)
        except Exception as err:
            journal.finish(db, run_id, "failed", {"error": repr(err)})
            raise
        journal.finish(db, run_id, report["status"], {k: v for k, v in report.items() if k in ("day", "stale", "calls_from", "note")})
    return report


def run(m, now: datetime, force: bool = False) -> dict:
    """`sp daily` by hand: gather, then crunch, in one go. It stops at 'waiting' while NSE's prices are not out (the timed
    crunch is what labels a stale day)."""
    report = gather(m, now, force)
    report["gather"] = {k: report[k] for k in list(report) if k in ("ingest", "kite", "docs", "pending", "failed")}
    report.update({k: report.pop(k) for k in ("ingest", "kite", "docs") if k in report})
    if report["status"] in ("holiday", "failed", "waiting"):
        return report
    crunched = crunch(m, now, force)
    return {**report, **crunched}
