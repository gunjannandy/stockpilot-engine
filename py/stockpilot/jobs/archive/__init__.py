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
