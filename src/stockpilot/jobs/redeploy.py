"""`sp redeploy` (issue #113): the v2 replacement for what sp-tick's ship step did for the site. A systemd oneshot timer runs it
every 15 minutes and it exits at once unless something is due:
  daily    the two slots (07:30 and 23:30 IST) so the public files that land overnight and in the morning (search index, universe,
           fund stats, charts, mechanical results) reach Pages;
  changed  the shipped paths on `main` (web/, the site builder) differ from what was last deployed.
It fast-forwards the checkout only (never reset, checkout, pull or rebase), builds the site (once; twice only if `sp verify` changed a price flag), and deploys through `ship.deploy_safe`
(scripts/cutover: the four hard blocks, then rollback). A failure leaves the live site as it was and is a problem row; the same
failure is not retried for two hours."""
import json
from datetime import datetime, timedelta, timezone

from stockpilot import journal, store
from stockpilot.jobs import ship

IST = timezone(timedelta(hours=5, minutes=30))
STATE = "data/redeploy-state.json"
SHIP_PATHS = ("web", "src/stockpilot/site.py", "src/stockpilot/site_export")   # what changes the deployed site
RUN_PATHS = ("web", "src", "config", "scripts", "ops")     # a change here is a real edit; docs/status/verify-<date>.md is not
SLOTS = ((7, 30), (23, 30))
BACKOFF = timedelta(hours=2)
KEY = "redeploy"
MAX_FILES = 19_500            # Cloudflare Pages allows 20,000 files a site; stop before it refuses the whole deploy


def last_slot(now: datetime) -> datetime:
    """The most recent slot at or before `now`."""
    now = now.astimezone(IST)
    today = [now.replace(hour=h, minute=m, second=0, microsecond=0) for h, m in SLOTS]
    past = [s for s in today if s <= now]
    return past[-1] if past else today[-1] - timedelta(days=1)


def _read(path) -> dict:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def _write(path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, sort_keys=True))
    tmp.replace(path)


def _problem(m, message: str, severity: str = "error") -> None:
    with m.db("redeploy") as db:
        journal.problem(db, "redeploy", message, severity, key=KEY)


def _resolve(m) -> None:
    with m.db("redeploy") as db:
        db.execute("update problems set resolution = 'a later deploy passed' "
                   "where job = 'redeploy' and resolution is null")


def update_checkout(m) -> str | None:
    """Fast-forward to origin/main, and only that. Returns why it could not, else None."""
    git = m.git
    try:
        git("fetch", "--quiet", "origin", "main")
        if git("rev-parse", "--abbrev-ref", "HEAD").strip() != "main":
            return "the checkout is not on main, so it was left alone"
        if git("status", "--porcelain", "--", *RUN_PATHS).strip():
            return "the checkout has uncommitted changes in a path that ships or runs, so it was left alone"
        git("merge", "--ff-only", "origin/main")
    except Exception as err:  # noqa: BLE001
        return f"the checkout could not fast-forward to main ({str(err)[-200:]})"
    return None


def fingerprint(m) -> str:
    return m.git("rev-parse", *[f"HEAD:{p}" for p in SHIP_PATHS]).replace("\n", " ").strip()


def _build(m, db, now) -> dict | None:
    """The same verified build the evening ship gates on; returns the second `sp verify` result."""
    _, verified = ship.build_verified(m, db, now.astimezone(IST).date(), now.replace(tzinfo=None))
    return verified


def run(m, now=None, build=None) -> dict:
    now = now or m.clock()
    now = now.astimezone(IST) if now.tzinfo else now.replace(tzinfo=IST)
    path = m.root / STATE
    state = _read(path)
    held = update_checkout(m)
    if held:
        _problem(m, f"Dashboard not redeployed: {held}.", "warning")
        return {"status": "held", "why": held}
    fp = fingerprint(m)
    slot = last_slot(now)
    ok_at = datetime.fromisoformat(state["ok_at"]) if state.get("ok_at") else None
    if ok_at is None or state.get("fp") != fp:
        reason = "changed" if state.get("fp") not in (None, fp) else "daily"
    elif ok_at < slot:
        reason = "daily"
    else:
        return {"status": "idle"}
    failed = state.get("failed")
    if failed and failed["fp"] == fp and now - datetime.fromisoformat(failed["at"]) < BACKOFF:
        return {"status": "backoff", "reason": reason}
    try:
        with ship.site_lock(m.root):
            with m.db("redeploy") as db:
                verified = (build or _build)(m, db, now)
            if verified and verified.get("hard_failed"):      # the deploy rule: a hard `sp verify` failure is a hard block
                raise RuntimeError(f"sp verify failed, so nothing was deployed ({verified.get('summary', '')})")
            count = sum(1 for f in (m.root / "site").rglob("*") if f.is_file())
            if count > MAX_FILES:
                raise RuntimeError(f"the site has {count} files; Pages allows 20,000, so nothing was deployed")
            note = m.deploy()
    except store.Busy:           # the evening job holds the store: it ships by itself, try again in 15 minutes
        return {"status": "busy"}
    except Exception as err:  # noqa: BLE001  the live site was not changed by a failed build, and a failed deploy rolled back
        message = str(err)[-400:]
        _problem(m, f"Dashboard not redeployed ({reason}): {message}")
        state["failed"] = {"fp": fp, "at": now.isoformat()}
        _write(path, state)
        return {"status": "failed", "reason": reason, "error": message}
    _write(path, {"fp": fp, "ok_at": now.isoformat()})
    _resolve(m)
    return {"status": "deployed", "reason": reason, "note": note}


def exit_code(report: dict) -> int:
    return {"failed": 2, "busy": 75}.get(report.get("status"), 0)      # 75: not a fault, the unit accepts it
