"""Ship: build the site, publish status, archive, deploy. The end of every daily run, and what a button press
that changes the page runs."""
import fcntl
import io
import json
import os
import shutil
import subprocess
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urlparse

from stockpilot import backup, journal, ops, store, weekly

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
    meta = site.build(db, cfg.root / out, today=today, budget_inr=cfg.get("budget.monthly_default_inr", 100000),
                      liquidity_floor_cr=cfg.get("universe.liquidity_floor_cr", 1.0), pack_dir=pack_dir(cfg), now=now,
                      tokens=token_list(cfg))
    ship_public_files(cfg, cfg.root / out)
    return meta


def d1_query(cfg):
    """D1 over HTTP for the VM's writes, or None when this machine has no Cloudflare keys (a test box, a fresh VM)."""
    account, token, database = cfg.secret("CLOUDFLARE_ACCOUNT_ID"), cfg.secret("CLOUDFLARE_API_TOKEN"), cfg.get("d1.database_id")
    if not (account and token and database):
        return None
    from stockpilot.jobs.minute import cloudflare_query
    return cloudflare_query(account, database, token)


def write_views(cfg, site_dir, now, query=None) -> str:
    """After a build: put Holdings, Tax and the record pages into D1 (#115). Never stops a ship; a failure is a Health problem."""
    from stockpilot import views
    query = query or d1_query(cfg)
    if query is None:
        return "skipped: no D1 keys on this machine"
    try:
        done = views.write_from_site(site_dir, query, now.astimezone(views.IST).replace(microsecond=0).isoformat(), now.date())
    except Exception as err:  # noqa: BLE001
        return f"failed: {type(err).__name__}"
    return "wrote " + ", ".join(done) if done else "nothing to write"


def ship_public_files(cfg, site_dir) -> None:
    """Release assets send no CORS header, so the public data files (search index, universe table, funds, mechanical
    results) ride along with the site. Off unless `public_data.repo` is set. A failure leaves the files already there."""
    repo = cfg.get("public_data.repo")
    if not repo:
        return
    from stockpilot.sources import public_files
    try:
        public_files.fetch_into(site_dir, repo, state=Path(cfg.root) / "data" / "public-files-state.json")
    except Exception:  # noqa: BLE001  a missing night of public data must not stop the dashboard deploying
        pass


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
    hide). Only when that verify changed the set of flagged symbols is the site rebuilt and verified again: otherwise the rebuild
    would be byte-for-byte the same site, so the first verify is the one that gates. Returns (the last build's meta, the gating
    verify's result). A hard failure of the gating verify is a hard block either way. A verify that cannot run is a problem row,
    not a stop: a broken checker must not freeze the dashboard. Off with `verify.on_ship: false`."""
    from stockpilot.verify import flags as verify_flags
    meta = build_site(db, m.cfg, today=day, now=now)
    if not m.cfg.get("verify.on_ship", True):
        return meta, None
    before = verify_flags.flagged_symbols(db)
    final = None
    for step in ("first", "final"):
        _release(db)                       # verify opens the store for writing itself
        try:
            final = run_verify(m, day, write=True)
        except Exception as err:  # noqa: BLE001
            journal.problem(db, "ship", f"verify ({step} pass) could not run: {err!r}", "error", key=f"verify-{step}")
            return meta, None
        if step == "first":
            if verify_flags.flagged_symbols(db) == before:
                break                      # no flag changed: a second build would write the same site
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


@contextmanager
def site_lock(root):
    """One build-and-deploy of `site/` at a time on the 1 GB VM: the evening ship and `sp redeploy` share this lock. A second
    one raises `store.Busy`, which both callers already treat as "not a fault, try again" (exit 75)."""
    path = Path(root) / "data" / "site.lock"
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = open(path, "w")
    try:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise store.Busy(None) from None
        yield
    finally:
        handle.close()


def node_path() -> str:
    found = os.environ.get("NODE") or shutil.which("node")
    if not found:
        raise RuntimeError("node was not found: the safe deploy (scripts/cutover) needs it on PATH or in $NODE")
    return found


DEPLOY_TIMEOUT_S = 3600      # wrangler uploads ~15,000 files from a swapping 1 GB VM, then the four checks drive a headless browser


def deploy_safe(cfg, run=subprocess.run, node: str | None = None, wrangler: str | None = None) -> str:
    """The deploy rule (orchestration-decisions section 3): `scripts/cutover/cutover.mjs deploy --target production` deploys,
    checks the four hard blocks on the new deployment and rolls production back on a failure. Raises with the reason, so the
    caller writes the problem row; the live site is then the one that was live before."""
    script = cfg.root / "scripts" / "cutover" / "cutover.mjs"
    done = run([node or node_path(), str(script), "deploy", "--target", "production"], cwd=cfg.root / "web",
               capture_output=True, text=True, env={**os.environ, "WRANGLER": wrangler or wrangler_path()}, timeout=DEPLOY_TIMEOUT_S)
    if done.returncode == 0:
        return "Dashboard deployed."
    out = (done.stdout or "") + (done.stderr or "")
    result = {}
    for line in reversed(out.strip().splitlines()):
        try:
            result = json.loads(line)
            break
        except ValueError:
            continue
    if done.returncode == 3 or result.get("stage") == "preflight":
        raise RuntimeError(f"preflight failed, nothing deployed: {out.strip()[-300:]}")
    failed = ", ".join(result.get("failed") or []) or result.get("error") or out.strip()[-200:]
    if result.get("error", "").startswith("rollback failed") or result.get("rolledBack") is False and result.get("failed"):
        raise RuntimeError(f"hard block {failed}; production was NOT rolled back: {result.get('error', '')}")
    if result.get("rolledBack"):
        raise RuntimeError(f"hard block {failed}; rolled back to the previous deployment")
    raise RuntimeError(f"deploy failed: {failed}")


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
    with site_lock(m.root):
        return _ship(m, db, now)


def _ship(m, db, now) -> dict:
    """The end of the daily run: score old calls, build the site, then (database let go) push status and the archive
    and deploy. A rerun runs it again; the archive refuses a day it already holds."""
    day = now.date()
    out = {"scored": record.score(db, day)}
    meta, verified = build_verified(m, db, day, now)
    out["site"] = meta["as_of"]
    out["views"] = write_views(m.cfg, m.root / "site", now)
    if out["views"].startswith("failed"):
        journal.problem(db, "ship", f"D1 views not written ({out['views']}); the screens use the static files.", key="views-write")
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
