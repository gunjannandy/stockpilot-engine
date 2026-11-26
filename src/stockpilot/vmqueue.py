"""`sp queue`: poll the Worker for requests the owners made on the dashboard, apply each, acknowledge it.
Each kind has one handler. A later stage adds its kind with @handler; an unknown kind fails with a clear note."""
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Callable

from stockpilot import feedback, learn, watchlist
from stockpilot.book import budget, not_now

HANDLERS = {}
NEEDS_CONTEXT = set()
from stockpilot.jobs.due import RERUNNABLE


@dataclass
class Context:
    """What the heavier handlers need from the machine. Each piece is injected, so tests need no network.
    `rerun(job)` asks the next tick to run a job again; the tick that is already running picks it up after the queue."""
    sync_docs: Callable | None = None      # (db) -> note: `sp trades sync`, which also rebuilds lots
    build_pack: Callable | None = None     # (db) -> note: tax pack for the current FY
    publish: Callable | None = None        # (db) -> note: build the site and deploy it
    gh: Callable | None = None             # gh(*args) -> stdout
    git: Callable | None = None            # git(*args) -> stdout
    rerun: Callable | None = None          # (job) -> None


def handler(kind, context=False):
    def register(fn):
        HANDLERS[kind] = fn
        if context:
            NEEDS_CONTEXT.add(kind)
        return fn
    return register


def _symbol(payload) -> tuple[str, str]:
    symbol, exchange = str(payload.get("symbol", "")).strip().upper(), str(payload.get("exchange", "NSE")).strip().upper()
    if not re.fullmatch(r"[A-Z0-9&-]{1,20}", symbol):
        raise ValueError(f"'{payload.get('symbol')}' is not a stock symbol.")
    if exchange == "AMFI":      # a mutual fund, by its ISIN (the fund research tab's star)
        if not re.fullmatch(r"INF[A-Z0-9]{9}", symbol):
            raise ValueError(f"'{symbol}' is not a fund code.")
        return symbol, exchange
    if exchange not in ("NSE", "BSE"):
        raise ValueError(f"Exchange must be NSE, BSE or AMFI, not '{exchange}'.")
    return symbol, exchange


@handler("watchlist_add")
def _watchlist_add(db, payload, by):
    symbol, exchange = _symbol(payload)
    return f"Added {symbol}." if watchlist.add(db, symbol, exchange, by) else f"{symbol} was already on the watchlist."


@handler("watchlist_remove")
def _watchlist_remove(db, payload, by):
    symbol, exchange = _symbol(payload)
    return f"Removed {symbol}." if watchlist.remove(db, symbol, exchange, by) else f"{symbol} was not on the watchlist."


ASK_ANALYST_PER_DAY = 5


@handler("long_term_mark")
def _long_term_mark(db, payload, by):
    symbol, _ = _symbol(payload)
    on = payload.get("on")
    if not isinstance(on, bool):
        raise ValueError("Say whether to mark it (on) or unmark it.")
    if on:
        db.execute("insert or ignore into long_term_marks (symbol, marked_by) values (?, ?)", [symbol, by])
        return f"{symbol} is marked as held for years."
    db.execute("delete from long_term_marks where symbol = ?", [symbol])
    return f"{symbol} is no longer marked as held for years."


@handler("ask_analyst")
def _ask_analyst(db, payload, by):
    symbol, _ = _symbol(payload)
    today = date.today()
    if db.execute("select count(*) from analyst_asks where symbol = ? and status = 'pending'", [symbol]).fetchone()[0]:
        return f"{symbol} is already waiting for the analyst."
    if db.execute("select count(*) from analyst_asks where asked_on = ?", [today]).fetchone()[0] >= ASK_ANALYST_PER_DAY:
        raise ValueError(f"Only {ASK_ANALYST_PER_DAY} questions to the analyst a day. Try again tomorrow.")
    db.execute("insert into analyst_asks (symbol, asked_by, asked_on) values (?, ?, ?)",
               [symbol, by, today])
    return f"The analyst will look at {symbol} at the next run."


@handler("budget_set")
def _budget_set(db, payload, by):
    month = str(payload.get("month", ""))
    amount = payload.get("amount_inr", payload.get("amount"))   # the dashboard posts `amount`
    budget.set_month(db, month, amount, by)
    return f"Budget for {month} is ₹{amount:,.0f}."


@handler("allocation_approve")
def _allocation_approve(db, payload, by):
    target = payload.get("target", payload) if isinstance(payload, dict) else None   # the dashboard wraps it
    if not isinstance(target, dict) or not target:
        raise ValueError("The target allocation is empty.")
    db.execute("insert into target_allocations (allocation, approved_by) values (?, ?)", [json.dumps(target), by])
    return "Target allocation approved."


@handler("not_now")
def _not_now(db, payload, by):
    symbol = str(payload.get("symbol", "")).strip().upper()
    scope = _scope(payload)
    not_now.set(db, symbol, scope, payload.get("for"), by, date.today())
    scope = {"buy": "buy calls", "sell": "sell calls", "any": "calls"}.get(scope, "calls")
    when = {"week": "for a week", "month": "for a month", "good": "for good"}[payload["for"]]
    return f"{symbol} is out of {scope} {when}."


def _scope(payload):
    """The page's clock and cross buttons say "stock": it has no buy or sell side, so the stock goes out of every call."""
    scope = payload.get("scope")
    return "any" if scope == "stock" else scope


def _set_aside(db, payload, by, how):
    symbol = str(payload.get("symbol", "")).strip().upper()
    scope = _scope(payload)
    not_now.set(db, symbol, scope, how, by, date.today())
    scope = {"buy": "buy calls", "sell": "sell calls", "any": "calls"}[scope]
    return f"{symbol} is hidden from {scope} for 30 days." if how == "snooze" else f"{symbol} is dismissed from {scope} until you undo it."


@handler("snooze")
def _snooze(db, payload, by):
    return _set_aside(db, payload, by, "snooze")


@handler("dismiss")
def _dismiss(db, payload, by):
    return _set_aside(db, payload, by, "dismiss")


@handler("not_now_undo")
def _not_now_undo(db, payload, by):
    ident = payload.get("id")
    if isinstance(ident, str) and ident.strip().isdigit():     # the page reads the id from a data- attribute, so it arrives as text
        ident = int(ident)
    not_now.undo(db, ident)
    return "Not now undone."


@handler("learned_forget")
def _learned_forget(db, payload, by):
    pattern = learn.forget(db, payload.get("pattern"), date.today())
    return f"Forgotten for {learn.FORGET_DAYS} days: {pattern}."


@handler("feedback", context=True)
def _feedback(db, payload, by, ctx):
    feedback.add(db, payload.get("text"), payload.get("kind"), by)
    return "Received. It is looked at in the evening." + _publish(db, ctx)


@handler("feedback_decide", context=True)
def _feedback_decide(db, payload, by, ctx):
    return feedback.decide(db, payload.get("id"), payload.get("decision"), ctx.gh) + _publish(db, ctx)


def _publish(db, ctx) -> str:
    if not ctx.publish:
        return ""
    try:
        return " " + ctx.publish(db)
    except Exception as err:  # noqa: BLE001 - the work is done; only the page refresh failed
        return f" The page refresh failed ({err}); the next daily run will retry."


@handler("refresh_docs", context=True)
def _refresh_docs(db, payload, by, ctx):
    if not ctx.sync_docs:
        raise ValueError("Document sync is not set up on this machine.")
    return ctx.sync_docs(db) + _publish(db, ctx)


@handler("rerun", context=True)
def _rerun(db, payload, by, ctx):
    job = str(payload.get("job", "daily"))
    if job not in RERUNNABLE:
        raise ValueError(f"'{job}' cannot be rerun from here.")
    if not ctx.rerun:
        raise ValueError("A rerun cannot be started on this machine.")
    ctx.rerun(job)
    return f"Running {job} again now. The page updates when it finishes."


@handler("build_tax_pack", context=True)
def _build_tax_pack(db, payload, by, ctx):
    if not ctx.build_pack:
        raise ValueError("The tax pack cannot be built on this machine.")
    return ctx.build_pack(db) + _publish(db, ctx)


def _ack(db, worker, row_id: int, remote_id: str, status: str, note: str):
    code, _ = worker.post("/api/vm/queue/ack", {"id": remote_id, "status": status, "note": note})
    if code == 200:
        db.execute("update requests set acked = true where id = ?", [row_id])


def _apply(db, item, ctx) -> tuple[str, str]:
    fn = HANDLERS.get(item["kind"])
    if not fn:
        return "failed", f"'{item['kind']}' cannot be done yet."
    try:
        args = (db, item.get("payload") or {}, item.get("by", ""))
        if item["kind"] in NEEDS_CONTEXT:
            if ctx is None:
                return "failed", f"'{item['kind']}' cannot be done on this machine."
            args += (ctx,)
        return "done", fn(*args)
    except ValueError as err:
        return "failed", str(err)
    except Exception as err:  # noqa: BLE001 - one bad request must not block the rest
        return "failed", f"Something went wrong: {err}"


STUCK_NOTE = "The machine stopped while doing this; press the button again."


def poll(db, worker, ctx: Context | None = None) -> dict:
    # A row still `received` when a poll starts was being applied when the machine died: it will never finish.
    db.execute("update requests set status = 'failed', note = ?, applied_at = current_timestamp "
               "where status = 'received'", [STUCK_NOTE])
    for row_id, remote_id, status, note in db.execute(
            "select id, remote_id, status, note from requests where remote_id is not null and not acked").fetchall():
        _ack(db, worker, row_id, remote_id, status, note or "")
    cursor = db.execute("select coalesce(max(remote_id), '') from requests").fetchone()[0]
    code, items = worker.get(f"/api/vm/queue?after={cursor}")
    if code != 200:
        raise RuntimeError(f"Worker queue answered {code}")
    counts = {"done": 0, "failed": 0}
    for item in sorted(items, key=lambda i: i["id"]):
        row_id = db.execute("insert into requests (kind, payload, status, remote_id, requested_by, acked) "
                            "values (?, ?, 'received', ?, ?, false) returning id",
                            [item["kind"], json.dumps(item.get("payload")), item["id"], item.get("by")]).fetchone()[0]
        status, note = _apply(db, item, ctx)
        db.execute("update requests set status = ?, note = ?, applied_at = current_timestamp where id = ?",
                   [status, note, row_id])
        counts[status] += 1
        _ack(db, worker, row_id, item["id"], status, note)
    return counts


RETIRE_AFTER_DAYS = 7


def retire_ready(worker, now, days: int = RETIRE_AFTER_DAYS) -> tuple[bool, str]:
    """Is the KV queue safe to delete (#114)? Yes when nothing waits and the page has not called it for `days` days.
    Returns (ready, plain words). A Worker that cannot say is never ready."""
    code, got = worker.get("/api/vm/queue/status")
    if code != 200:
        return False, f"The Worker could not say (answered {code})."
    if got.get("pending"):
        return False, f"{got['pending']} requests still wait in the KV queue."
    last = got.get("last_call_at")
    if last:
        quiet = now - datetime.fromisoformat(last.replace("Z", "+00:00"))
        if quiet < timedelta(days=days):
            return False, f"The page called the KV queue {quiet.days} days ago; wait for {days} quiet days."
    return True, f"No call to the KV queue for {days} days and nothing waiting: safe to retire."
