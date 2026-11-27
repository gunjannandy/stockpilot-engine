"""Idempotent writes: a rerun of the same range must leave the same rows.

Row ids come from the row's own natural key, never from the run or the clock, and a batch is
de-duplicated and ordered before it is sent.
"""
import hashlib
import json


def row_id(*parts: object) -> str:
    """A stable id from a natural key, e.g. row_id("holiday", "2026-12-25")."""
    text = "|".join(json.dumps(p, sort_keys=True, default=str) for p in parts)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def stable_rows(rows: list[dict], key: str = "id") -> list[dict]:
    """One row per id (the last one wins), in id order, so two runs send the same batch."""
    by_id: dict[str, dict] = {}
    for row in rows:
        by_id[str(row[key])] = row
    return [by_id[k] for k in sorted(by_id)]
