"""MOVE-1: tools/move/ rebuilds the v3 layout from today's engine in one run."""
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKSPACES = ["contract", "money", "api", "web", "adapters"]
GONE = ["site", "site_export", "vmqueue", "orchestrate", "cli", "weekly", "review", "feedback_read", "views",
        "list_writers", "ops", "machine"]
KEPT = ["backup", "vault", "migrate_v2", "trades/lots", "trades/corporate_actions", "analysis/tax", "trades/rsu",
        "book", "store", "publish"]


# The merge commit of the move. Facts true only at the move are checked there, so later tickets may edit and delete.
MOVED = "f995340"


@pytest.fixture(scope="module")
def moved(tmp_path_factory):
    path = tmp_path_factory.mktemp("moved") / "tree"
    subprocess.run(["git", "worktree", "add", "--detach", str(path), MOVED], cwd=ROOT, check=True, capture_output=True)
    yield path
    subprocess.run(["git", "worktree", "remove", "--force", str(path)], cwd=ROOT, check=True, capture_output=True)


def test_the_python_lives_in_py():
    assert (ROOT / "py/pyproject.toml").is_file()
    assert (ROOT / "py/stockpilot/__init__.py").is_file()
    assert (ROOT / "py/tests").is_dir()
    assert not (ROOT / "src").exists() and not (ROOT / "tests").exists() and not (ROOT / "pyproject.toml").exists()


def test_the_workspace_has_five_empty_shells():
    ws = (ROOT / "pnpm-workspace.yaml").read_text()
    for name in WORKSPACES:
        assert f"- {name}\n" in ws
        assert (ROOT / name / "package.json").is_file()
    assert (ROOT / "tsconfig.base.json").is_file() and (ROOT / "biome.json").is_file()
    assert '"strict": true' in (ROOT / "tsconfig.base.json").read_text()


def test_what_decisions_mark_deleted_is_gone():
    for m in GONE:
        assert not (ROOT / f"py/stockpilot/{m}.py").exists() and not (ROOT / f"py/stockpilot/{m}").exists(), m


def test_the_move_kept_the_money_and_backup_modules(moved):
    for m in KEPT:
        p = moved / f"py/stockpilot/{m}"
        assert p.is_dir() or p.with_suffix(".py").is_file(), m


def test_the_move_put_v2_web_and_workflows_under_legacy(moved):
    assert (moved / "legacy/web/package.json").is_file() and not (ROOT / "web/functions").exists()
    assert len(list((moved / "legacy/workflows").glob("*.yml"))) == 12


def test_the_move_script_reproduces_the_moved_tree(moved):
    r = subprocess.run([sys.executable, "tools/move/move.py", "--check"], cwd=moved, capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr
