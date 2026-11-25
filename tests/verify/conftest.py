"""Shared fixtures for the verify tests: a small temp DB, built by hand, and a site built from the seeded fixture DB."""
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from stockpilot import store


@pytest.fixture
def db(tmp_path):
    return store.open(tmp_path / "v.duckdb")


@pytest.fixture(scope="module")
def site_built(tmp_path_factory):
    """The seeded DB (with lane A's extras), a built site, and the day: what most checks run against.
    Set VERIFY_SITE_CACHE=<folder> while developing to build it once and reuse it (the checks never write to it)."""
    import os
    import shutil
    from site_export_seed import seed
    from seed_site import AS_OF, TOKENS
    from stockpilot import site
    cache = os.environ.get("VERIFY_SITE_CACHE")
    if cache and (Path(cache) / "site" / "data" / "meta.json").exists():
        root = tmp_path_factory.mktemp("verify_site")
        shutil.copy(Path(cache) / "sp.duckdb", root / "sp.duckdb")
        return store.open(root / "sp.duckdb"), Path(cache) / "site", AS_OF
    root = Path(cache) if cache else tmp_path_factory.mktemp("verify_site")
    root.mkdir(parents=True, exist_ok=True)
    db = seed(root / "sp.duckdb")
    out = root / "site"
    site.build(db, out, today=AS_OF, budget_inr=100000, now=datetime(2026, 11, 20, 19, 30), tokens=TOKENS)
    if cache:
        db.close()
        shutil.copy(root / "sp.duckdb", root / "sp.duckdb.bak")
        scratch = tmp_path_factory.mktemp("verify_site")
        shutil.copy(root / "sp.duckdb", scratch / "sp.duckdb")
        return store.open(scratch / "sp.duckdb"), out, AS_OF
    return db, out, AS_OF
