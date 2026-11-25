"""Encrypted copies of the database, in two kinds.

Owner state (cannot be rebuilt) goes to `private/state/<table>.parquet`; the vault then encrypts and pushes it.
Market data (rebuildable, but hours of downloading) is exported to parquet, encrypted file by file to the vault
public key, and uploaded to a GitHub release. Encryption streams (pyrage works file to file), so memory stays low.
Every outside call (gh, the upload, the download) is passed in, so tests need no network.
"""
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable

import pyrage
from pyrage import passphrase, x25519

from stockpilot import vault

TAG = "market-backup"

# Cannot be rebuilt from public data.
STATE_TABLES = ["watchlist", "budgets", "target_allocations", "calls", "requests", "problems", "runs",
                "holdings", "kite_syncs", "trades", "lots", "sales", "weekly_reports", "documents", "holding_statements",
                "not_now", "archived_days", "fund_calls",
                "smallcase_orders", "trade_tags", "payslip_perquisites", "action_terms", "feedback", "learned_forgotten",
                "console_pnl_totals", "console_pnl", "itr_documents", "fidelity_events", "feedback_changes", "gaps",
                "long_term_marks", "analyst_asks", "house_rule_edits", "fidelity_holdings", "fidelity_lots"]
# Tables added after the first state backups were written: an older backup has no file for them, and a restore
# starts them empty. A core table (trades, lots, calls...) missing is still a refusal.
ADDED_LATER = ["not_now", "archived_days", "fund_calls", "smallcase_orders", "trade_tags", "payslip_perquisites",
               "action_terms", "feedback", "learned_forgotten", "console_pnl_totals", "console_pnl", "itr_documents", "fidelity_events", "feedback_changes", "gaps",
               "long_term_marks", "analyst_asks", "house_rule_edits", "fidelity_lots"]
# Rebuildable, but slow to download. A table added in store.MIGRATIONS must be in one list (a test checks).
MARKET_TABLES = ["prices", "fundamentals", "holidays", "surveillance", "funds", "navs", "fx", "announcements",
                 "index_levels", "stocks", "base_rates", "corporate_actions", "fetch_log", "fund_costs",
                 "delivery", "deals", "results_calendar", "flows", "filings_index", "headlines", "quarterly", "screens",
                 "base_rate_buckets", "fund_base_rates", "ownership", "price_flags", "demerger_factors"]

# Tables with an id from a sequence: after a load the sequence must start past the loaded ids.
SEQUENCES = {"lots": "lot_id", "runs": "run_id", "calls": "call_id", "requests": "request_id",
             "problems": "problem_id", "target_allocations": "allocation_id", "trades": "trade_id",
             "sales": "sale_id", "not_now": "not_now_id", "feedback": "feedback_id",
             "fund_calls": "fund_call_id", "analyst_asks": "analyst_ask_id", "house_rule_edits": "house_rule_id"}


class BackupError(RuntimeError):
    pass


def _export(db, table: str, path: Path) -> int:
    db.execute(f"copy (select * from {table}) to '{path}' (format parquet, compression zstd)")
    return db.execute(f"select count(*) from {table}").fetchone()[0]


def _load(db, table: str, path: Path) -> int:
    db.execute(f"insert into {table} by name select * from read_parquet('{path}')")
    return db.execute(f"select count(*) from {table}").fetchone()[0]


def _require_empty(db, tables) -> None:
    full = [t for t in tables if db.execute(f"select count(*) from {t}").fetchone()[0]]
    if full:
        raise BackupError(f"Refusing to load into a store that already has rows in: {', '.join(full)}.")


def export_state(db, out_dir: Path | str) -> dict:
    """`sp backup state`: one zstd parquet per owner table."""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    return {t: _export(db, t, out / f"{t}.parquet") for t in STATE_TABLES}


def load_state(db, in_dir: Path | str) -> dict:
    """`sp backup load-state`: read the parquet files into an empty store, ids intact."""
    src = Path(in_dir)
    absent = [t for t in STATE_TABLES if not (src / f"{t}.parquet").exists()]
    missing = [t for t in absent if t not in ADDED_LATER]
    if missing:
        raise BackupError(f"No state file for: {', '.join(missing)} (looked in {src}).")
    _require_empty(db, STATE_TABLES)
    counts = {t: _load(db, t, src / f"{t}.parquet") for t in STATE_TABLES if t not in absent}
    for table, seq in SEQUENCES.items():
        top = db.execute(f"select coalesce(max(id), 0) from {table}").fetchone()[0]
        while db.execute(f"select nextval('{seq}')").fetchone()[0] <= top:
            pass
    return counts


def backup_market(db, recipient: str, upload: Callable[[str, list[Path]], None],
                  work_dir: Path | str | None = None) -> dict:
    """`sp backup market`: export, encrypt to the vault public key, upload. Plaintext never outlives the call."""
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="sp-backup-"))
    work.mkdir(parents=True, exist_ok=True)
    key = [x25519.Recipient.from_str(recipient)]
    counts, files = {}, []
    try:
        for table in MARKET_TABLES:
            plain = work / f"{table}.parquet"
            counts[table] = _export(db, table, plain)
            sealed = work / f"{table}.parquet.age"
            pyrage.encrypt_file(str(plain), str(sealed), key)
            plain.unlink()
            files.append(sealed)
        manifest = work / "manifest.json"
        manifest.write_text(json.dumps({"tables": counts}, indent=1))
        upload(TAG, files + [manifest])
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return counts


def restore_market(db, sealed_identity: bytes, password: str, download: Callable[[str, Path], None],
                   work_dir: Path | str | None = None) -> dict:
    """`sp backup restore-market`: download, open with the vault identity, load into an empty store."""
    try:
        identity = x25519.Identity.from_str(passphrase.decrypt(sealed_identity, password).decode())
    except Exception as err:  # pyrage raises its own DecryptError
        raise vault.VaultError("Could not open the vault key: wrong password or a damaged key.") from err
    _require_empty(db, MARKET_TABLES)
    work = Path(work_dir) if work_dir else Path(tempfile.mkdtemp(prefix="sp-restore-"))
    work.mkdir(parents=True, exist_ok=True)
    counts = {}
    try:
        download(TAG, work)
        for table in MARKET_TABLES:
            sealed = work / f"{table}.parquet.age"
            if not sealed.exists():
                raise BackupError(f"The release has no {sealed.name}.")
            plain = work / f"{table}.parquet"
            pyrage.decrypt_file(str(sealed), str(plain), [identity])
            sealed.unlink()
            counts[table] = _load(db, table, plain)
            plain.unlink()
    finally:
        shutil.rmtree(work, ignore_errors=True)
    return counts


def _gh(run, *argv, check=True):
    return run(["gh", *argv], capture_output=True, text=True, check=check)


def gh_upload(tag: str, paths: list[Path], run=subprocess.run) -> None:
    """Upload to the release `tag` (made if missing), replace same-named assets, drop assets not in this set."""
    if _gh(run, "release", "view", tag, "--json", "assets", check=False).returncode != 0:
        _gh(run, "release", "create", tag, "--title", "Market data backup (encrypted)",
            "--notes", "Encrypted with config/vault.pub. Restore with `sp backup restore-market`.")
    for path in paths:
        _gh(run, "release", "upload", tag, str(path), "--clobber")
    listing = _gh(run, "release", "view", tag, "--json", "assets").stdout
    keep = {p.name for p in paths}
    for asset in json.loads(listing or "{}").get("assets", []):
        if asset["name"] not in keep:
            _gh(run, "release", "delete-asset", tag, asset["name"], "--yes")


def gh_download(tag: str, dest: Path, run=subprocess.run) -> None:
    _gh(run, "release", "download", tag, "--dir", str(dest), "--clobber")
