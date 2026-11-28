"""The backup and drill Jobs for D1: nightly encrypted snapshot to the vault branch, monthly restore proof.

Both run in private workflows (a Worker cannot do either inside 10 ms of CPU). Every outside call is passed in
(the D1 source and target, the report, the beat), so tests need no network. Plaintext lives only in a work folder
that is deleted whatever happens. The backup writes one JSON-lines file per table and a manifest of row counts and
checksums; the drill restores the vault, checks each file against the manifest, loads it into the preview D1 and
compares counts.
"""
import hashlib
import json
import shutil
from collections.abc import Callable, Iterable
from datetime import timedelta
from pathlib import Path
from typing import Protocol

from stockpilot import vault

KIND = "backup"
DRILL_KIND = "drill"
FOLDER = "d1"
# A beat is due a little after the next run: nightly plus two hours, monthly plus three days.
DUE = {"job.backup": timedelta(days=1, hours=2), "job.drill": timedelta(days=34)}
_INTERNAL = ("sqlite_", "_cf_")
_SKIP = {"d1_migrations"}

Report = Callable[[dict], None]
Beat = Callable[..., None]


class DrillError(RuntimeError):
    pass


class Source(Protocol):
    def tables(self) -> list[str]: ...
    def pages(self, table: str) -> Iterable[list[dict]]: ...


class Target(Protocol):
    def replace(self, table: str, rows: list[dict]) -> None: ...
    def count(self, table: str) -> int | None: ...


def wanted(table: str) -> bool:
    return not table.startswith(_INTERNAL) and table not in _SKIP


def _line(row: dict) -> str:
    return json.dumps(row, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _write_table(path: Path, pages: Iterable[list[dict]]) -> dict:
    sha, rows = hashlib.sha256(), 0
    with path.open("w", encoding="utf-8", newline="\n") as out:
        for page in pages:
            for row in page:
                text = _line(row) + "\n"
                out.write(text)
                sha.update(text.encode())
                rows += 1
    return {"rows": rows, "sha256": sha.hexdigest()}


def _read_table(path: Path) -> tuple[list[dict], str]:
    data = path.read_bytes()
    return [json.loads(x) for x in data.decode().splitlines()], hashlib.sha256(data).hexdigest()


def _now() -> str:
    from stockpilot.io.clock import ist_now, ist_text
    return ist_text(ist_now())


def backup(source: Source, remote: str, keys: "vault.Keys", work: Path | str, report: Report, beat: Beat) -> dict:
    """Snapshot every table, encrypt, push one vault commit, then report and beat. Returns table -> rows."""
    work = Path(work)
    try:
        folder = work / FOLDER
        folder.mkdir(parents=True)
        tables = {t: _write_table(folder / f"{t}.jsonl", source.pages(t)) for t in sorted(source.tables()) if wanted(t)}
        (folder / "manifest.json").write_text(json.dumps({"tables": tables}, indent=1, sort_keys=True))
        vault.push(work, remote, keys, [FOLDER])
    except Exception as err:
        beat("job.backup", ok=False, error=str(err))
        raise
    finally:
        shutil.rmtree(work, ignore_errors=True)
    report({"kind": KIND, "at": _now(), "ok": True, "tables": tables, "detail": f"{len(tables)} tables"})
    beat("job.backup", ok=True)
    return {t: v["rows"] for t, v in tables.items()}


def drill(target: Target, remote: str, password: str, scratch: Path | str, report: Report, beat: Beat) -> dict:
    """Restore the vault, load it into `target` (the preview D1), compare every table's count. Raises DrillError."""
    scratch = Path(scratch)
    tables: dict = {}
    try:
        try:
            vault.restore(remote, password, scratch)
            folder = scratch / FOLDER
            tables = json.loads((folder / "manifest.json").read_text())["tables"]
            wrong = []
            for t, want in tables.items():
                rows, sha = _read_table(folder / f"{t}.jsonl")
                if sha != want["sha256"] or len(rows) != want["rows"]:
                    wrong.append(f"{t} (file differs from the manifest)")
                    continue
                if target.count(t) is None:
                    wrong.append(f"{t} (not in the target database)")
                    continue
                target.replace(t, rows)
                if target.count(t) != want["rows"]:
                    wrong.append(f"{t} (loaded {target.count(t)} of {want['rows']} rows)")
        finally:
            shutil.rmtree(scratch, ignore_errors=True)
        if wrong:
            raise DrillError("The restore does not match the backup for: " + ", ".join(wrong) + ".")
    except Exception as err:
        report({"kind": DRILL_KIND, "at": _now(), "ok": False, "tables": tables, "detail": str(err)})
        beat("job.drill", ok=False, error=str(err))
        raise
    report({"kind": DRILL_KIND, "at": _now(), "ok": True, "tables": tables, "detail": f"{len(tables)} tables match"})
    beat("job.drill", ok=True)
    return {"ok": True, "tables": {t: v["rows"] for t, v in tables.items()}}
