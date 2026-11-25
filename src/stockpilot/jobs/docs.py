"""Document sync: new broker mail and Drive files into trades and lots."""
import json
from datetime import timedelta
from pathlib import Path

from stockpilot import journal


def _fund_isins(db) -> dict:
    """Fund name (letters and digits only, lower case) -> growth ISIN, from the NAV list and from past MF trades."""
    def norm(name):
        return "".join(c for c in name.lower() if c.isalnum())
    out = {norm(n): i for n, i in db.execute("select name, isin_growth from funds where isin_growth is not null").fetchall()}
    for n, i in db.execute("select symbol, isin from trades where kind = 'mf' and isin is not null").fetchall():
        out.setdefault(norm(n), i)
    return lambda name: out.get(norm(name))


def _documents(n: int) -> str:
    return f"{n} document" + ("" if n == 1 else "s")


def _failures_by_cause(db, failed: list) -> None:
    """One problem per cause, not per document: 230 mails refused for the same reason are one line on the Health tab."""
    groups: dict[str, list[str]] = {}
    for ident, why in failed:
        cause = str(why)
        if cause.startswith(f"{ident}: "):
            cause = cause[len(ident) + 2:]
        groups.setdefault(cause, []).append(ident)
    for cause, ids in groups.items():
        journal.problem(db, "trades", f"{cause}: {_documents(len(ids))} (for example {', '.join(ids[:3])})",
                        key=f"docs:{cause}"[:240])


def _release(db) -> None:
    """The bridge can take minutes: let go of the writer lock while it works (a Lease takes it back on next use)."""
    getattr(db, "suspend", lambda: None)()


def mark_acted(db) -> str:
    """R5: after new trades arrive (documents or Kite), mark the calls they acted on. A failure is a problem, never a stop."""
    from stockpilot.book import acted
    try:
        n = acted.mark(db)
    except Exception as err:  # noqa: BLE001 - the sync is done; detection tries again next sync
        journal.problem(db, "acted", f"acted-on detection: {err!r}")
        return ""
    return f" {n} call{'' if n == 1 else 's'} marked acted on." if n else ""


def sync_docs(db, bridge, pan: str, since: str | None = None) -> str:
    return sync_batch(db, bridge, pan, since)[0]


def sync_batch(db, bridge, pan: str, since: str | None = None, limit: int | None = None,
               now=None) -> tuple[str, bool]:
    """`sp trades sync`: pull new mail and Drive files, store the trades, rebuild lots and sales.
    The first run reads all history; later runs read from the last clean sync (a run with a failure does not move it,
    so the failed document is tried again). With `limit`, at most that many documents are read; the second value says
    some are left, and the next call takes them (a document already handled is skipped, so no work repeats)."""
    from datetime import datetime, timezone
    from stockpilot.trades import feed, lots
    started = (now or (lambda: datetime.now(timezone.utc)))()
    if since is None:       # the window starts at the last listing that worked, so a queue of waiting downloads never re-lists history
        last = db.execute("select max(period) from fetch_log where source in ('docs', 'docs_listed')").fetchone()[0]
        since = (datetime.fromisoformat(last) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ") if last else None
    done = set(db.execute("select id, version from documents").fetchall())
    isin_of = _fund_isins(db)
    _release(db)
    result = feed.fetch(bridge, pan, since, isin_of=isin_of, done=done, limit=limit)
    stale = getattr(bridge, "stale", "")
    if result.deferred:
        journal.problem(db, "trades", f"Gmail daily limit reached: {_documents(len(result.deferred))} wait for the next sync.",
                        key="gmail-quota")
    if not stale and not result.failed:   # the bridge answered: all up to now is in the local listing, whatever waits to download (a failed document keeps the window open)
        db.execute("insert or replace into fetch_log values ('docs_listed', ?)", [started.isoformat()])
    if not (result.failed or result.deferred or stale or result.more):   # a listing from the disk copy, or a partial pass, leaves the window open
        db.execute("insert or replace into fetch_log values ('docs', ?)", [started.isoformat()])
    if stale:
        journal.problem(db, "trades", f"Document list came from the local copy; the bridge said: {stale}")
    if not (result.handled or result.failed):
        if result.deferred:
            return f"Documents: {_documents(len(result.deferred))} wait for the next sync (Gmail daily limit).", False
        return "Documents: no change since the last sync; nothing parsed.", False
    added = feed.store_all(db, result)
    for st in (s for s in result.statements if s.as_of):
        for isin, qty in st.closing.items():
            db.execute("insert or replace into holding_statements values (?, ?, ?)", [st.as_of, isin, qty])
    for row in result.handled:   # last: a document is marked handled only once what it gave is stored
        db.execute("insert or replace into documents (id, source, kind, name, version, outcome, reason, trades) "
                   "values ($id, $source, $kind, $name, $version, $outcome, $reason, $trades)", row)
    outcome = lots.rebuild(db)
    as_of, gaps = lots.check_against_statement(db)
    for isin, held, ours in gaps:
        journal.problem(db, "trades", f"{isin}: the depository statement of {as_of} shows {held:g}, the lots hold {ours:g}.")
    note = (f"Documents synced: {added} new trades, {len(result.ignored)} ignored on purpose, {len(result.skipped)} of "
            f"unknown kind, {len(result.failed)} could not be read. {outcome.lots} lots.")
    if gaps:
        note += f" {len(gaps)} holdings differ from the depository statement of {as_of}."
    if result.deferred:
        note += f" {len(result.deferred)} wait for the next sync (Gmail daily limit)."
    _failures_by_cause(db, result.failed)
    for isin, day, qty in outcome.unmatched_sells:
        journal.problem(db, "trades", f"Sell of {qty:g} {isin} on {day} has no lot to match (baseline tradebook incomplete?).")
    return note + mark_acted(db), result.more


def sync_safely(m, db, job: str, limit: int | None = None) -> tuple[str, bool]:
    """Document sync inside a job: a gap (no secrets, the bridge down) is a warning, never a stop."""
    from stockpilot import config
    try:
        bridge, pan = m.bridge()
        return sync_batch(db, bridge, pan, limit=limit)
    except Exception as err:  # noqa: BLE001
        why = str(err) if isinstance(err, config.MissingSecrets) else repr(err)
        journal.problem(db, job, f"document sync skipped: {why}", key="docs-skipped")
        return f"Document sync skipped: {why}", False


def bridge_from(cfg):
    from stockpilot.sources import google
    secrets = cfg.require("GOOGLE_BRIDGE_URL", "GOOGLE_BRIDGE_KEY", "OWNER_PAN")
    bridge = google.Bridge(secrets["GOOGLE_BRIDGE_URL"], secrets["GOOGLE_BRIDGE_KEY"])
    cache = Path(cfg.get("docs.cache_dir", "~/sp-docs")).expanduser()   # private documents: never under the repo
    return google.Cache(bridge, cache), secrets["OWNER_PAN"]
