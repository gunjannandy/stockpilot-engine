"""The archive Job: rows older than the archive age leave D1 for Parquet before a cap is hit.

The Parquet file is written and counted first; only then are the rows deleted, so a failure
loses nothing. Reads and deletes are passed in (tests need no network).
"""
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

import duckdb

KIND = "archive"
ARCHIVE_AGE_DAYS = 400


def archive(dataset: str, rows: list[dict], out_dir: Path | str, today: date,
            delete: Callable[[list[dict]], None], age_days: int = ARCHIVE_AGE_DAYS) -> dict:
    """Move rows whose `day` is older than `age_days` to `<out_dir>/<dataset>-<cutoff>.parquet`, then delete them."""
    cutoff = (today - timedelta(days=age_days)).isoformat()
    old = [r for r in rows if str(r["day"]) < cutoff]
    if not old:
        return {"moved": 0, "file": None}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"{dataset}-{cutoff}.parquet"
    db = duckdb.connect()
    try:
        db.execute("create table t (day varchar, body varchar)")
        db.executemany("insert into t values (?, ?)", [(str(r["day"]), str(r.get("body", ""))) for r in old])
        db.execute(f"copy t to '{path}' (format parquet, compression zstd)")
        written = db.execute(f"select count(*) from read_parquet('{path}')").fetchone()[0]
    finally:
        db.close()
    if written != len(old):
        path.unlink(missing_ok=True)
        raise RuntimeError("The Parquet file does not hold every row; nothing was deleted.")
    delete(old)
    return {"moved": len(old), "file": str(path)}


class Table:
    """What the handler needs of one archivable table: read its rows, delete the ones that moved."""

    def read(self, table: str) -> list[dict]: ...
    def delete(self, table: str, rows: list[dict]) -> None: ...


# Tables that archive. None yet: a table joins here when it has a `day` and a body to keep (see archive()).
TABLES: dict[str, Table] = {}


def run(ctx, tables: dict[str, Table] | None = None, out_dir: Path | str = "archive-out") -> str:
    """The runtime handler: archive every registered table; a failure raises and the Job ends failed."""
    tables = TABLES if tables is None else tables
    today = ctx.range.end
    moved = touched = 0
    for name, src in tables.items():
        out = archive(name, src.read(name), out_dir, today, lambda rows, n=name, s=src: s.delete(n, rows))
        if out["moved"]:
            moved += out["moved"]
            touched += 1
            ctx.progress.line(f"{name}: {out['moved']} rows moved to {out['file']}", "ok")
    if not moved:
        return "nothing to archive: no table is past the archive age"
    return f"archived {moved} rows from {touched} tables"
