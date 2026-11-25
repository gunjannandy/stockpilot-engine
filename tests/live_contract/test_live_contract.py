"""The v2 live data contract (ticket T0, issue #26).

`schemas/live-contract.json` is the one contract every v2 lane builds against: D1 tables, Pages API routes,
job kinds, progress lines, published file formats and the nightly write budget. These tests check that the
fixtures under `tests/fixtures/live/` match it, that the D1 migration builds exactly the tables it names,
and that one night's writes stay under half of D1's daily limit.
"""
import json
import re
import sqlite3
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = json.loads((ROOT / "schemas" / "live-contract.json").read_text())
FIX = ROOT / "tests" / "fixtures" / "live"
MIGRATIONS = sorted((ROOT / "web" / "migrations").glob("*.sql"))

D1_DAILY_WRITE_LIMIT = 100_000
FAKE_SYMBOLS = {"FIXA", "FIXB", "FIXC", "FIXD", "NIFTY", "SENSEX"}


def load(rel):
    return json.loads((FIX / rel).read_text())


def check(value, shape, path="$"):
    """Return a list of problems. Shape language is described in the contract's `shape_language`."""
    if isinstance(shape, dict):
        if not isinstance(value, dict):
            return [f"{path}: expected object, got {type(value).__name__}"]
        bad = []
        for key, sub in shape.items():
            optional = key.endswith("?")
            name = key[:-1] if optional else key
            if name not in value:
                if not optional:
                    bad.append(f"{path}.{name}: missing")
                continue
            bad += check(value[name], sub, f"{path}.{name}")
        known = {k[:-1] if k.endswith("?") else k for k in shape}
        bad += [f"{path}.{extra}: not in contract" for extra in value if extra not in known]
        return bad
    if isinstance(shape, list):
        if not isinstance(value, list):
            return [f"{path}: expected list, got {type(value).__name__}"]
        bad = []
        for i, item in enumerate(value):
            bad += check(item, shape[0], f"{path}[{i}]")
        return bad
    nullable = shape.endswith("?")
    base = shape[:-1] if nullable else shape
    if value is None:
        return [] if nullable else [f"{path}: null not allowed"]
    if base == "str":
        ok = isinstance(value, str)
    elif base == "int":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif base == "num":
        ok = isinstance(value, (int, float)) and not isinstance(value, bool)
    elif base == "bool":
        ok = isinstance(value, bool)
    elif base == "json":
        ok = True
    elif base == "date":
        ok = isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None
    elif base == "time":
        ok = isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+05:30", value) is not None
    elif base.startswith("enum("):
        ok = value in base[5:-1].split("|")
    else:
        raise AssertionError(f"{path}: unknown type {shape!r} in contract")
    return [] if ok else [f"{path}: {value!r} is not {shape}"]


def table_shape(table):
    return {c: t for c, t in CONTRACT["tables"][table]["columns"].items()}


# ---- tables ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("table", sorted(CONTRACT["tables"]))
def test_every_table_has_fixture_rows_that_match(table):
    rows = load(f"tables/{table}.json")
    assert rows, f"{table}: fixture has no rows"
    problems = [p for i, row in enumerate(rows) for p in check(row, table_shape(table), f"{table}[{i}]")]
    assert not problems, "\n".join(problems)


def test_no_fixture_table_is_missing_from_the_contract():
    on_disk = {p.stem for p in (FIX / "tables").glob("*.json")}
    assert on_disk == set(CONTRACT["tables"])


def test_migrations_build_exactly_the_contract_tables_and_take_every_fixture_row():
    assert MIGRATIONS, "no D1 migration under web/migrations"
    db = sqlite3.connect(":memory:")
    for m in MIGRATIONS:
        db.executescript(m.read_text())
    built = {r[0] for r in db.execute("select name from sqlite_master where type='table' and name not like 'sqlite_%'")}
    assert built == set(CONTRACT["tables"])
    for table, spec in CONTRACT["tables"].items():
        cols = {r[1] for r in db.execute(f"pragma table_info({table})")}
        assert cols == set(spec["columns"]), f"{table}: migration columns differ from contract"
        for row in load(f"tables/{table}.json"):
            names = list(row)
            db.execute(
                f"insert into {table} ({','.join(names)}) values ({','.join('?' * len(names))})",
                [json.dumps(v) if isinstance(v, (dict, list)) else v for v in row.values()],
            )
        for idx in spec.get("indexes", []):
            assert any(
                [c[2] for c in db.execute(f"pragma index_info({i[1]})")] == idx
                for i in db.execute(f"pragma index_list({table})")
            ), f"{table}: index {idx} missing from migration"


# ---- routes ---------------------------------------------------------------------------------------------

@pytest.mark.parametrize("route", CONTRACT["routes"], ids=lambda r: r["id"])
def test_every_route_has_a_fixture_with_request_and_response_that_match(route):
    fx = load(f"routes/{route['id']}.json")
    assert set(fx) == {"request", "response"}
    problems = []
    if route["request"] is None:
        assert fx["request"] is None
    else:
        problems += check(fx["request"], route["request"], "request")
    problems += check(fx["response"], route["response"], "response")
    assert not problems, "\n".join(problems)


def test_route_ids_are_unique_and_every_fixture_belongs_to_a_route():
    ids = [r["id"] for r in CONTRACT["routes"]]
    assert len(ids) == len(set(ids))
    assert {p.stem for p in (FIX / "routes").glob("*.json")} == set(ids)


def test_every_route_names_who_may_call_it():
    for r in CONTRACT["routes"]:
        assert r["auth"] in {"person", "owner", "ingest"}, r["id"]
        assert r["method"] in {"GET", "POST"}, r["id"]
        assert r["path"].startswith("/api/v2/"), r["id"]


# ---- jobs -----------------------------------------------------------------------------------------------

def test_job_kinds_name_who_runs_them_and_their_payload_keys():
    kinds = CONTRACT["job_kinds"]
    assert {"sync", "analyse", "refresh_call", "feedback_read", "news_tag", "load_stock", "nightly"} <= set(kinds)
    for name, spec in kinds.items():
        assert spec["runs_on"] in {"vm_model", "vm_private", "github_public"}, name
        assert isinstance(spec["payload"], list), name


def test_job_fixtures_use_known_kinds_and_progress_lines_match():
    kinds = set(CONTRACT["job_kinds"])
    for job in load("tables/jobs.json"):
        assert job["kind"] in kinds
        assert set(json.loads(job["payload"]) if isinstance(job["payload"], str) else job["payload"]) <= set(
            CONTRACT["job_kinds"][job["kind"]]["payload"]
        )
    lines = load("tables/job_lines.json")
    seq = {}
    for ln in lines:
        seq.setdefault(ln["job_id"], []).append(ln["seq"])
    for job_id, s in seq.items():
        assert s == list(range(1, len(s) + 1)), f"job {job_id}: progress lines must count 1,2,3 with no gaps"


# ---- published files ------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", sorted(CONTRACT["files"]))
def test_every_published_file_has_a_fixture_that_matches(name):
    spec = CONTRACT["files"][name]
    problems = check(load(f"files/{name}.json"), spec["shape"], name)
    assert not problems, "\n".join(problems)


def test_chart_history_columns_have_one_length():
    h = load("files/chart_history.json")
    n = len(h["dates"])
    for col in ("open", "high", "low", "close", "volume", "dma50", "dma200"):
        assert len(h[col]) == n, col
    assert h["dates"] == sorted(h["dates"])


# ---- no private data ------------------------------------------------------------------------------------

def test_fixtures_hold_only_made_up_symbols_and_no_contact_details():
    text = "".join(p.read_text() for p in FIX.rglob("*.json"))
    assert not re.search(r"[\w.+-]+@[\w-]+\.\w+", text), "an email address is in a fixture"
    symbols = set(re.findall(r'"symbol": "([^"]+)"', text))
    assert symbols and symbols <= FAKE_SYMBOLS, symbols - FAKE_SYMBOLS


# ---- write budget ---------------------------------------------------------------------------------------

def test_one_night_of_writes_stays_under_half_of_the_d1_daily_limit():
    b = CONTRACT["write_budget"]
    assert b["daily_limit"] == D1_DAILY_WRITE_LIMIT
    total = 0
    for item in b["items"]:
        table = item["table"]
        per_row = 1 + len(CONTRACT["tables"][table].get("indexes", []))  # D1 counts each index entry as a row written
        total += item["rows"] * per_row
    assert total == b["estimated_total"], f"estimate in contract says {b['estimated_total']}, items add to {total}"
    assert total <= D1_DAILY_WRITE_LIMIT / 2
    assert total <= b["warn_at"] <= b["stop_at"] <= D1_DAILY_WRITE_LIMIT


def test_write_budget_covers_every_table_that_gets_written_by_a_job():
    covered = {i["table"] for i in CONTRACT["write_budget"]["items"]}
    assert set(CONTRACT["tables"]) - covered <= set(CONTRACT["write_budget"]["rarely_written"])


def test_probe_findings_from_t2_are_in_the_contract():
    """docs/research/probes-v2.md: what the T2 probes changed."""
    c = CONTRACT
    probes = c["probes"]
    # 1. Browsers cannot read release assets (no CORS), so static files go through Pages.
    assert probes["release_assets_to_browser"] == "never"
    assert all(f["served_by"] == "pages" for f in c["files"].values())
    # 2. Thumbnails read at most the first 100 KB of the article page.
    og = next(r for r in c["routes"] if r["id"] == "og_image")
    assert og["read_limit_bytes"] == 102400
    # 3. The simulated night wrote about 10,000 rows with few indexes; the estimate must stay under half the limit.
    assert probes["d1_night_rows_simulated"] <= c["write_budget"]["daily_limit"] // 2
    # 4. Quotes: Worker timer first, public Actions poll as the named fallback.
    assert probes["quote_path"] == {"primary": "worker_timer", "fallback": "github_public_poll"}
