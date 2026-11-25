"""Lane B, the one real run: Fidelity documents -> events -> RSU trades -> lots, rates and US prices, then the unit check.

    python scripts/lane_b_real_run.py --db data/stockpilot.duckdb --backup-dir ~/backups/lane-B --report out.json
    python scripts/lane_b_real_run.py --db /scratch/copy.duckdb --dry-run     # a copy of the database: same steps, no backup

It holds the database writer lock for the whole run (a timer job that has it makes this stop), reads the owner's PAN from
.env without printing it, reads documents only from the private disk copy (no Gmail, no Drive), and prints counts, never
quantities or amounts. Re-running it adds nothing."""
import argparse
import json
import shutil
import sys
import urllib.request
from datetime import date, datetime
from pathlib import Path

from stockpilot import store
from stockpilot.book import positions, rsu, units
from stockpilot.jobs import fidelity
from stockpilot.sources import fx, usprices
from stockpilot.trades import lots


def pan_from(env_file: Path) -> str:
    for line in env_file.read_text().splitlines():
        if line.startswith("OWNER_PAN="):
            return line.split("=", 1)[1].strip().strip("\"'")
    raise SystemExit("OWNER_PAN is not in the env file")


def fetch(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=60) as r:   # noqa: S310 - Frankfurter, a fixed https URL
        return r.read()


def counts(db, today: date) -> dict:
    q = lambda sql: db.execute(sql).fetchone()[0]   # noqa: E731
    held = positions.held(db, today)
    return {
        "fidelity_documents": dict(db.execute("select outcome, count(*) from documents where kind = 'fidelity' group by 1").fetchall()),
        "fidelity_events": dict(db.execute("select kind, count(*) from fidelity_events group by 1").fetchall()),
        "rsu_trades": dict(db.execute("select side, count(*) from trades where kind = 'rsu' group by 1").fetchall()),
        "rsu_lots": q("select count(*) from lots where kind = 'rsu'"),
        "lots_total": q("select count(*) from lots"),
        "fx_rows": q("select count(*) from fx where pair = 'USDINR'"),
        "now_price_rows": q("select count(*) from prices where symbol = 'NOW'"),
        "split_actions": q("select count(*) from corporate_actions where symbol = 'NOW'"),
        "held_by_kind": {k: sum(1 for p in held if p.kind == k) for k in sorted({p.kind for p in held})},
        "held_total": len(held),
        "unit_gaps": len(units.gaps(db)),
        "open_unit_problems": q("select count(*) from problems where job = 'units' and resolution is null"),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", required=True)
    ap.add_argument("--docs", default="~/sp-docs")
    ap.add_argument("--env", default="/home/ubuntu/stockpilot/.env")
    ap.add_argument("--backup-dir", default="")
    ap.add_argument("--report", default="")
    ap.add_argument("--dry-run", action="store_true", help="the database is a copy: skip the backup")
    ap.add_argument("--no-network", action="store_true", help="skip the rate and US price downloads")
    args = ap.parse_args()
    today, steps = date.today(), {}
    db = store.open(args.db, job="lane_b", wait_s=0)
    try:
        before = counts(db, today)
        if not args.dry_run:
            if not args.backup_dir:
                raise SystemExit("a real run needs --backup-dir")
            out = Path(args.backup_dir).expanduser() / datetime.now().strftime("%Y%m%d-%H%M%S")
            out.mkdir(parents=True)
            from stockpilot import backup
            steps["backup_state_tables"] = len(backup.export_state(db, out / "state"))
            db.execute("checkpoint")
            shutil.copy2(args.db, out / "stockpilot.duckdb")
            steps["backup_dir"] = out.name
        res = fidelity.ingest(db, Path(args.docs).expanduser(), pan_from(Path(args.env)))
        steps["ingest"] = {"documents": res["documents"], "events": res["events"], "ignored": len(res["ignored"]),
                           "failed": [reason for _, reason in res["failed"]]}
        steps["bridge_new_trades"] = rsu.bridge(db)
        steps["lots_rebuilt"] = lots.rebuild(db).lots
        year = usprices.first_year(db)
        if year and not args.no_network:
            try:
                steps["fx_rates_stored"] = fx.ingest_usdinr_range(db, date(year, 1, 1), today, fetch)
            except Exception as err:   # noqa: BLE001 - the weekly job tries again; the run goes on
                steps["fx_error"] = repr(err)[:200]
            try:
                steps["us_prices_stored"] = usprices.refresh(db, usprices.yahoo_history, today)
            except Exception as err:   # noqa: BLE001
                steps["us_prices_error"] = repr(err)[:200]
        units.record(db)
        after = counts(db, today)
    finally:
        db.close()
    report = {"before": before, "steps": steps, "after": after}
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps(report, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
