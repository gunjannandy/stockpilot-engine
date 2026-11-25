"""Ship: build the site, publish status, archive, deploy. The end of every daily run, and what a button press
that changes the page runs."""
import io
import json
import os
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

from stockpilot import backup, journal, ops, weekly

from stockpilot.calls import record


def project_name(cfg) -> str:
    return cfg.get("worker.project") or (urlparse(cfg.get("worker.url", "")).hostname or "stockpilot").split(".")[0]


def pack_dir(cfg) -> Path:
    return cfg.root / cfg.get("tax.pack_dir", "data/tax_pack")


def build_tax_pack(db, cfg, as_of: date | None = None) -> str:
    """Build the tax pack for the current FY and hand its summary to the dashboard."""
    as_of = as_of or date.today()
    private = weekly.load_private(cfg.root)
    payload = weekly.tax_section(db, as_of, pack_dir(cfg), private)
    weekly.store_section(db, as_of, "tax", payload)
    return f"Tax pack for {payload['fy']} is built."


def token_list(cfg) -> list[dict]:
    """Config `tokens` become the countdowns on the Health tab."""
    out = []
    for name, spec in (cfg.get("tokens") or {}).items():
        expires = date.fromisoformat(str(spec["issued"])) + timedelta(days=spec.get("lifetime_days", 365))
        out.append({"name": name, "expires_on": str(expires)})
    return out


def build_site(db, cfg, out: str = "site", today: date | None = None, now=None) -> dict:
    from stockpilot import site
    today = today or date.today()
    return site.build(db, cfg.root / out, today=today, budget_inr=cfg.get("budget.monthly_default_inr", 100000),
                      liquidity_floor_cr=cfg.get("universe.liquidity_floor_cr", 1.0), pack_dir=pack_dir(cfg), now=now,
                      tokens=token_list(cfg))


def run_verify(m, day: date, *, write: bool = True) -> dict:
    """`sp verify` against the built site, in this process. With `write` it first syncs the price flags (the store is opened for
    writing, so the caller must have let the database go). Returns {hard_failed, summary}; opens GitHub issues when `m.gh` is set."""
    from stockpilot.verify import run as verify_run
    out = io.StringIO()
    code = verify_run.run(m.cfg, db_path=m.db_path, site=m.root / "site", day=day, read_only=not write,
                          issues=m.gh is not None, gh=m.gh, out=out)
    return {"hard_failed": code, "summary": out.getvalue().strip().replace("\n", " ")[:300]}


def build_verified(m, db, day: date, now=None) -> tuple[dict, dict | None]:
    """The deploy order: build the site, `sp verify` with write access (it writes the price flags the first build could not
    hide), rebuild, `sp verify` again. Returns (the second build's meta, the second verify's result). Only the second verify
    gates the deploy. A verify that cannot run is a problem row, not a stop: a broken checker must not freeze the dashboard.
    Off with `verify.on_ship: false`."""
    meta = build_site(db, m.cfg, today=day, now=now)
    if not m.cfg.get("verify.on_ship", True):
        return meta, None
    final = None
    for step in ("first", "final"):
        _release(db)                       # verify opens the store for writing itself
        try:
            final = run_verify(m, day, write=True)
        except Exception as err:  # noqa: BLE001
            journal.problem(db, "ship", f"verify ({step} pass) could not run: {err!r}", "error", key=f"verify-{step}")
            return meta, None
        if step == "first":
            meta = build_site(db, m.cfg, today=day, now=now)
    return meta, final


def wrangler_path() -> str:
    """The absolute path of wrangler: what the install recorded in $WRANGLER, else what PATH finds now. A timer's PATH is short,
    so a bare `wrangler` once failed there with 'command not found'."""
    found = os.environ.get("WRANGLER") or shutil.which("wrangler")
    if not found:
        raise RuntimeError("wrangler was not found: run ops/install.sh again (it records the path) or set deploy.command")
    return found


def deploy_site(cfg, run=subprocess.run) -> str:
    """`wrangler pages deploy ../site` from web/. Raises if wrangler fails, so callers can log a problem."""
    cmd = list(cfg.get("deploy.command") or ["wrangler", "pages", "deploy", "../site", "--project-name", project_name(cfg)])
    if cmd[0] == "wrangler":
        cmd[0] = wrangler_path()
    done = run(cmd, cwd=cfg.root / "web", capture_output=True, text=True)
    if done.returncode != 0:
        raise RuntimeError(f"wrangler exited {done.returncode}: {(done.stderr or done.stdout or '')[-300:]}")
    return "Dashboard deployed."


def _release(db) -> None:
    getattr(db, "suspend", lambda: None)()


def deploy(m, db) -> str:
    """wrangler, with the database let go. A failure is a problem row on the Health tab (and raised); the next run retries."""
    _release(db)
    try:
        return m.deploy()
    except Exception as err:  # noqa: BLE001
        journal.problem(db, "deploy", f"deploy: {err}", "error")
        raise RuntimeError(f"deploy failed: {err}") from err


def publish(m, db, today: date | None = None) -> str:
    """Build the site, then deploy it."""
    meta = build_site(db, m.cfg, today=today)
    return f"Site built (prices as of {meta['as_of']}). {deploy(m, db)}"


# ---- the vault, only when owner data changed ------------------------------------------------------------

LOG_TABLES = {"runs", "problems"}      # they change on every job; the vault gets them whenever something real changed


def state_fingerprint(db) -> str:
    """Row counts of the owner tables, and the highest id where a table has one."""
    out = {}
    for table in backup.STATE_TABLES:
        if table in LOG_TABLES:
            continue
        top = ", max(id)" if table in backup.SEQUENCES else ""
        out[table] = list(db.execute(f"select count(*){top} from {table}").fetchone())
    return json.dumps(out, sort_keys=True)


def protect_state(m, db, job: str) -> str:
    """Owner tables to private/state/, then the vault push, but only when a table changed since the last push.
    A failure is a warning, never a stop: the job's own work is already stored."""
    if not (m.cfg.root / "config" / "vault.pub").exists() or m.push_vault is None:
        return "no vault"
    fingerprint = state_fingerprint(db)
    last = db.execute("select period from fetch_log where source = 'vault'").fetchone()
    if last and last[0] == fingerprint:
        return "unchanged"
    try:
        backup.export_state(db, m.cfg.root / "private" / "state")
        getattr(db, "releasing", lambda f: f)(m.push_vault)()      # the git push needs no database
        db.execute("delete from fetch_log where source = 'vault'")
        db.execute("insert into fetch_log values ('vault', ?)", [fingerprint])
    except Exception as err:  # noqa: BLE001
        journal.problem(db, job, f"state backup: {err!r}")
        return f"failed: {err!r}"
    return "pushed"


def ops_cfg(cfg) -> dict:
    return {"tokens": cfg.get("tokens"), "freshness": cfg.get("freshness")}


def ship(m, db, now) -> dict:
    """The end of the daily run: score old calls, build the site, then (database let go) push status and the archive
    and deploy. A rerun runs it again; the archive refuses a day it already holds."""
    day = now.date()
    out = {"scored": record.score(db, day)}
    meta, verified = build_verified(m, db, day, now)
    out["site"] = meta["as_of"]
    status = ops.build_status(db, ops_cfg(m.cfg), now, m.root)
    payload = ops.archive_payload(db, day, m.root)
    out["vault"] = protect_state(m, db, "daily")
    _release(db)
    for name, push in (("status", lambda: m.push_status(status)),
                       ("archive", lambda: payload and m.push_archive(day, payload) and ops.freeze_day(db, day))):
        try:
            push()
        except Exception as err:  # noqa: BLE001
            journal.problem(db, "ship", f"{name} push: {err!r}", key=f"push-{name}")
            out[name] = f"failed: {err!r}"
    if verified and verified["hard_failed"]:         # the deploy rule: a hard failure of `sp verify` is a hard block
        out["deploy"] = f"held back: sp verify failed ({verified['summary']})"
        journal.problem(db, "ship", f"Dashboard not deployed: {out['deploy']}", "error", key="verify-blocked")
        return out
    try:
        out["deploy"] = deploy(m, db)
    except RuntimeError as err:
        out["deploy"] = str(err)
    return out
