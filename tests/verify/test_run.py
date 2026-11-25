"""`sp verify` end to end on a small store file: exit code, summary line, report file, gaps and one issue per failed check."""
import io
import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

from vhelpers import DAY, price_rows
from helpers import insert_prices
from stockpilot import cli, store
from stockpilot.verify import report, run as verify_run


class FakeGh:
    def __init__(self):
        self.open, self.calls = [], []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("issue", "list"):
            return json.dumps([{"number": i + 1, "title": t} for i, t in enumerate(self.open)])
        if args[:2] == ("issue", "create"):
            title = args[args.index("--title") + 1]
            self.open.append(title)
            return f"https://github.invalid/issues/{len(self.open)}\n"
        return ""


def cfg_for(root):
    return SimpleNamespace(root=root, get=lambda key, default=None: default)


@pytest.fixture
def store_file(tmp_path):
    path = tmp_path / "data" / "sp.duckdb"
    path.parent.mkdir()
    db = store.open(path)
    db.execute("insert into stocks values ('TCS', 'Tata Consultancy Services', 'IT', 'INE467B01029')")
    db.execute("insert into holdings values ('2026-11-20 18:00:00', 'equity', 'TCS', 'INE467B01029', 10, 3000, 'kite')")
    db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, source) values "
               "('stock', 'TCS', 'INE467B01029', '2024-01-02', 7, 3000, 'tradebook')")           # 3 units unexplained
    insert_prices(db, price_rows("BROKEN", [100.0] * 90 + [20.0] * 30))
    db.execute("insert into stocks values ('BROKEN', 'Broken Ltd', 'X', 'INEBROKEN01')")
    db.close()
    return path


def go(tmp_path, path, gh, **kw):
    out = io.StringIO()
    code = verify_run.run(cfg_for(tmp_path), db_path=path, day=DAY, gh=gh, only={2, 3}, report_dir=tmp_path / "status", out=out, **kw)
    return code, out.getvalue()


def test_a_hard_failure_exits_non_zero_writes_the_report_opens_one_issue_and_records_gaps(tmp_path, store_file):
    gh = FakeGh()
    code, text = go(tmp_path, store_file, gh)
    assert code == 1
    assert "1 of 2 checks pass, 1 hard fail (2)" in text and f"verify-{DAY}.md" in text and len(text.strip().splitlines()) == 1
    md = (tmp_path / "status" / f"verify-{DAY}.md").read_text()
    assert "TCS: Kite shows 10 units" in md and "[verify] check 2" in md
    assert gh.open == ["[verify] check 2: Units explained by lots equal Kite's units"]           # check 3 passed: the flag handled it
    db = store.open(store_file)
    assert {(a, s) for a, s, *_ in db.execute("select area, subject from gaps where resolved_at is null").fetchall()} == {("holdings", "TCS"), ("price_history", "BROKEN")}
    db.close()


def test_a_second_run_opens_no_duplicate_issue_and_a_fixed_problem_closes_its_gap(tmp_path, store_file):
    gh = FakeGh()
    go(tmp_path, store_file, gh)
    go(tmp_path, store_file, gh)
    assert len(gh.open) == 1
    db = store.open(store_file)
    db.execute("update lots set quantity = 10")
    db.close()
    code, text = go(tmp_path, store_file, gh)
    assert code == 0 and "no hard fail" in text
    db = store.open(store_file)
    assert [s for _, s in db.execute("select area, subject from gaps where resolved_at is null").fetchall()] == ["BROKEN"]
    db.close()


def test_only_soft_failures_exit_zero(tmp_path, store_file):
    code, text = verify_run.run(cfg_for(tmp_path), db_path=store_file, day=DAY, gh=FakeGh(), only={11}, report_dir=tmp_path / "status",
                                out=(out := io.StringIO())) or (0, "")
    assert code == 0                                   # check 11 has nothing to compare, and soft anyway


def test_json_flag_prints_the_results(tmp_path, store_file):
    code, text = go(tmp_path, store_file, FakeGh(), as_json=True)
    body = json.loads(text)
    assert body["ok"] is False and body["hard_failed"] == [2] and body["results"][0]["id"] == 2 and body["report"].endswith(f"verify-{DAY}.md")


def test_read_only_leaves_the_store_untouched(tmp_path, store_file):
    code, text = go(tmp_path, store_file, FakeGh(), read_only=True)
    assert code == 1 and "check 3" not in text.lower()
    db = store.open(store_file)
    assert db.execute("select count(*) from gaps").fetchone()[0] == 0 and db.execute("select count(*) from price_flags").fetchone()[0] == 0
    db.close()
    assert "Read-only run" in (tmp_path / "status" / f"verify-{DAY}.md").read_text()


def test_the_cli_has_a_verify_command_with_the_gate_flags():
    parser_help = cli.main.__doc__ or ""
    import argparse
    import subprocess
    import sys
    out = subprocess.run([sys.executable, "-m", "stockpilot.cli", "verify", "--help"], capture_output=True, text=True).stdout
    for flag in ("--site", "--json", "--read-only", "--no-issues", "--previous", "--only"):
        assert flag in out


def test_a_first_write_pass_does_not_fail_check_3_for_flags_not_written_yet(tmp_path, store_file):
    """Deploy order (lane P2): a read-only pass on a fresh store fails check 3 ("not flagged yet"); the write pass that comes first
    in the ship step syncs the flags before it checks, so that failure cannot happen there."""
    _, readonly = go(tmp_path, store_file, FakeGh(), read_only=True, as_json=True)
    assert [r["status"] for r in json.loads(readonly)["results"] if r["id"] == 3] == ["fail"]
    code, written = go(tmp_path, store_file, FakeGh(), as_json=True)
    assert [r["status"] for r in json.loads(written)["results"] if r["id"] == 3] == ["pass"]
