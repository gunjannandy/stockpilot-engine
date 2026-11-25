"""The whole universe: every stock in search.json opens with a chart and key numbers; the build is fast and byte-stable."""
import json
import time
from datetime import datetime

import pytest

from seed_site import AS_OF, TOKENS
from site_export_seed import add_universe, seed
from stockpilot import site

NOW = datetime(2026, 11, 20, 19, 30)


@pytest.fixture(scope="module")
def big(tmp_path_factory):
    root = tmp_path_factory.mktemp("big")
    db = seed(root / "sp.duckdb")
    add_universe(db, 1520)
    t0 = time.monotonic()
    site.build(db, root / "a", today=AS_OF, budget_inr=100000, now=NOW, tokens=TOKENS)
    secs = time.monotonic() - t0
    site.build(db, root / "b", today=AS_OF, budget_inr=100000, now=NOW, tokens=TOKENS)
    site.build(db, root / "c", today=AS_OF, budget_inr=100000, now=datetime(2026, 11, 20, 19, 45), tokens=TOKENS)
    return root, secs


def test_all_1617_stocks_open_with_a_chart_and_key_numbers(big):
    root, _ = big
    search = json.loads((root / "a/data/search.json").read_text())
    assert len(search) >= 1617
    for s in search:
        sym = s["symbol"]
        h = json.loads((root / f"a/data/history/{sym}.json").read_text())
        assert len(h["close"]) >= 2 and len(h["volume"]) == len(h["close"])
        k = json.loads((root / f"a/data/stock/{sym}.json").read_text())
        assert k["close"] and k["range52"]["high"] and k["volume"]["last"]


def test_size_and_file_count_stay_inside_cloudflare_pages_limits(big):
    root, _ = big
    files = [p for p in (root / "a").rglob("*") if p.is_file()]
    assert len(files) < 20000
    assert max(p.stat().st_size for p in files) < 25 * 1024 * 1024
    assert sum(p.stat().st_size for p in (root / "a/data/history").glob("*.json")) < 40 * 1024 * 1024


def test_site_build_is_under_a_minute(big):
    assert big[1] < 60


def test_second_run_is_byte_stable(big):
    root, _ = big
    names = sorted(p.relative_to(root / "a") for p in (root / "a").rglob("*") if p.is_file())
    assert names == sorted(p.relative_to(root / "b") for p in (root / "b").rglob("*") if p.is_file())
    for n in names:
        assert (root / "a" / n).read_bytes() == (root / "b" / n).read_bytes(), n


def test_only_meta_clock_fields_differ_at_another_time(big):
    root, _ = big
    for p in (root / "a").rglob("*"):
        if p.is_file() and p.name != "meta.json":
            assert p.read_bytes() == (root / "c" / p.relative_to(root / "a")).read_bytes(), p
