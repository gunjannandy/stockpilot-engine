"""`sp verify`: sync the price flags, run the eleven checks read-only, record gaps, write the report, open the issues."""
import json
import sys
from datetime import date
from pathlib import Path

import duckdb

from stockpilot import store
from stockpilot.calls.decide import Rules
from stockpilot.verify import Ctx, flags, report, run_all

WRITE_WAIT_S = 120.0


def _open_read_only(path: Path):
    db = duckdb.connect(str(path), read_only=True)
    db.execute("set memory_limit = '350MB'")
    db.execute("set threads = 2")
    return db


def make_ctx(cfg, db, day: date, site, previous, briefs, rerun_backtest: bool) -> Ctx:
    return Ctx(db=db, day=day, site=Path(site) if site else None, previous_site=Path(previous) if previous else None,
               briefs=Path(briefs) if briefs else cfg.root / cfg.get("briefs.dir", "data/briefs"), root=cfg.root,
               rules=Rules.from_config(cfg), budget_default=cfg.get("budget.monthly_default_inr", 100000),
               liquidity_floor_cr=cfg.get("universe.liquidity_floor_cr", 1.0), sector_index=dict(cfg.get("sector_index") or {}),
               run_backtest=rerun_backtest)


def run(cfg, *, db_path: Path, site=None, previous=None, briefs=None, day: date | None = None, read_only: bool = False,
        issues: bool = True, gh=None, only=None, rerun_backtest: bool = False, report_dir=None, as_json: bool = False, out=None) -> int:
    """0 when no check failed hard, 1 otherwise. Prints one summary line (or the JSON) and the report path."""
    out = out or sys.stdout
    day = day or date.today()
    notes = []
    if not read_only:
        with store.open(db_path, job="verify", wait_s=WRITE_WAIT_S) as db:     # short: only the flags are written here
            synced = flags.sync(db, day)
        notes.append(f"Price flags synced: {len(synced)} series with an unexplained jump are excluded and hidden.")
    else:
        notes.append("Read-only run: price flags and gaps were not written.")
    db = _open_read_only(db_path)
    try:
        results = run_all(make_ctx(cfg, db, day, site, previous, briefs, rerun_backtest), only)
    finally:
        db.close()
    if not read_only:
        with store.open(db_path, job="verify", wait_s=WRITE_WAIT_S) as wdb:
            recorded, closed = report.record_gaps(wdb, results)
        notes.append(f"Gaps ledger: {recorded} recorded, {closed} closed.")
    opened = []
    if issues:
        opened = report.open_issues(results, day, gh or _gh(cfg.root))
    path = report.write(results, day, Path(report_dir) if report_dir else cfg.root / "docs" / "status", opened, notes)
    if as_json:
        print(json.dumps({**report.payload(results, day), "report": str(path), "issues": opened}, default=str), file=out)
    else:
        print(report.summary_line(results, day, path), file=out)
    return 1 if report.counts(results)["hard_failed"] else 0


def _gh(root):
    from stockpilot.jobs import doctor
    return doctor.gh_cli(root)
