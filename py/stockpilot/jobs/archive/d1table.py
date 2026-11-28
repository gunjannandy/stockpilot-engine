"""An archivable table in D1: old rows are read newest-safe (past the archive age only) and deleted by key."""
import json
import os

from stockpilot.jobs.backup.d1 import D1, _q

BATCH = 50


class D1Table:
    """`day_sql` turns a row into its YYYY-MM-DD; `key` is the column that names a row for deletion."""

    def __init__(self, d1: D1, day_sql: str, key: str, age_days: int):
        self.d1, self.day_sql, self.key, self.age_days = d1, day_sql, key, age_days

    def read(self, table: str) -> list[dict]:
        rows = self.d1.query(
            f"select *, {self.day_sql} as _day from {_q(table)} where {self.day_sql} < date('now', ?)",
            [f"-{self.age_days} day"])
        return [{"day": r["_day"], "body": json.dumps({k: v for k, v in r.items() if k != "_day"}, sort_keys=True),
                 "key": r[self.key]} for r in rows]

    def delete(self, table: str, rows: list[dict]) -> None:
        keys = [r["key"] for r in rows]
        for i in range(0, len(keys), BATCH):
            chunk = keys[i:i + BATCH]
            self.d1.query(f"delete from {_q(table)} where {_q(self.key)} in ({', '.join('?' * len(chunk))})", chunk)


def from_env(env=None, age_days: int = 400) -> dict[str, D1Table]:
    """The registered tables, live only when the D1 credentials are present (otherwise: nothing to archive)."""
    env = os.environ if env is None else env
    need = ("CF_ACCOUNT_ID", "D1_PRODUCTION_ID", "CF_D1_ARCHIVE_TOKEN")
    if not all(env.get(k) for k in need):
        return {}
    d1 = D1(env["CF_ACCOUNT_ID"], env["D1_PRODUCTION_ID"], env["CF_D1_ARCHIVE_TOKEN"])
    return {"browser_errors": D1Table(d1, "substr(at, 1, 10)", "id", age_days)}
