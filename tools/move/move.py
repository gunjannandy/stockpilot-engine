#!/usr/bin/env python3
"""Rebuild the v3 layout from the v2 engine tree. Rerunnable and reviewable.

    python tools/move/move.py --base <git-ref> --out <empty-dir>

Exports <git-ref> (the last v2 commit) into <out> and applies the move there:
  src/stockpilot -> py/stockpilot, tests -> py/tests, pyproject/uv.lock -> py/,
  v2 workflows -> legacy/workflows, v2 web/ -> legacy/web, the Python decisions
  section 3 marks deleted removed with their tests, and the pnpm workspace shells added.
Everything not named here is carried over untouched. `--check` re-runs the move
into a temp dir and diffs it against the working tree (see checks/MOVE-layout).
"""
from __future__ import annotations

import argparse
import ast
import io
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE / "templates"

# Modules of src/stockpilot that decisions section 3 marks deleted (VM path and dropped features).
# Kept for now because surviving Python still imports them: store, readiness, house_rules,
# learn, jobs/vmjobs, verify/ (rules not yet dataset checks), publish (deny-list not yet in CI).
DELETE_MODULES = [
    "site", "site_export", "vmqueue", "orchestrate", "cli", "weekly", "review",
    "feedback_read", "views", "list_writers", "ops", "machine",
    "jobs/ship", "jobs/weekly", "jobs/buttons", "jobs/daily", "jobs/doctor", "jobs/minute",
    "verify/run", "jobs/nav", "jobs/queue", "jobs/redeploy", "jobs/tick", "jobs/wire",
]
# Tests of the deleted VM path that name no deleted module (they read its files or run its units).
DELETE_TESTS = [
    "site_export", "queue", "orchestrate", "test_site.py", "test_wrangler_path.py", "test_dashboard_e2e.py",
    "test_integration_weekly_site.py", "test_integration_queue.py", "test_integration_weekly.py",
    "jobs/test_wire.py", "test_heartbeat.py", "test_busy.py", "test_store_lock.py", "test_reruns.py",
    "build_site_v10.py", "build_fixture_site.py", "live_contract",
    "audit_vm_rows.py", "jobs/test_ship_verify.py",
    # VM-path tests that share their fixtures with deleted tests, or drive the deleted units
    "test_machine.py", "test_archive_branch.py", "jobs/test_minute.py", "jobs/test_vmjobs.py",
    "jobs/test_weekly_job.py", "jobs/test_redeploy.py", "jobs/test_list_writers.py", "jobs/test_in_the_news.py",
    "jobs/test_ask_tickets.py", "test_house_rules.py", "sources/test_fundcosts.py", "test_migrate_v2.py",
    "verify/test_reasoning_checks.py", "verify/test_data_checks.py",
]
# Single tests that need the deleted VM machine or the v2 web contract tests.
DELETE_TEST_FUNCS = [
    "test_the_base_rates_job_runs_the_monthly_backtest_through_the_machine",
    "test_published_files_pass_the_live_contract_shapes",
]
WORKFLOWS_KEEP = {"ci.yml"}


def export(base: str, out: Path) -> None:
    data = subprocess.run(["git", "archive", base], check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        tar.extractall(out, filter="data")


def mod_path(root: Path, mod: str) -> list[Path]:
    return [p for p in (root / f"{mod}.py", root / mod) if p.exists()]


def rm(p: Path) -> None:
    shutil.rmtree(p) if p.is_dir() else p.unlink()


def imports(path: Path) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(ast.parse(path.read_text())):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom) and n.module is not None and not n.level:
            out.add(n.module)
            out |= {f"{n.module}.{a.name}" for a in n.names}
    return {i for i in out if i.startswith("stockpilot")}


def dotted(mod: str) -> str:
    return "stockpilot." + mod.replace("/", ".")


def hits(imps: set[str], dead: set[str]) -> bool:
    return any(i == d or i.startswith(d + ".") for i in imps for d in dead)


def _dead_names(node: ast.AST, dead: set[str]) -> set[str]:
    """Local names an import statement binds to a deleted module (or its members)."""
    names: set[str] = set()
    if isinstance(node, ast.ImportFrom) and node.module and not node.level:
        for a in node.names:
            if hits({node.module, f"{node.module}.{a.name}"}, dead) and not (
                    node.module == "stockpilot" and f"stockpilot.{a.name}" not in dead):
                names.add(a.asname or a.name)
    elif isinstance(node, ast.Import):
        for a in node.names:
            if hits({a.name}, dead):
                names.add((a.asname or a.name).split(".")[0])
    return names


def prune_test(path: Path, dead: set[str], gone: set[str]) -> None:
    """`gone`: names of fixtures and helpers cut so far (conftest files are pruned first)."""
    src = path.read_text()
    tree = ast.parse(src)
    lines = src.splitlines(keepends=True)
    # names bound by module-level imports of deleted modules
    mod_dead: set[str] = set()
    for n in tree.body:
        mod_dead |= _dead_names(n, dead)

    def uses_dead(n: ast.AST) -> bool:
        for sub in ast.walk(n):
            if _dead_names(sub, dead):
                return True
            if isinstance(sub, ast.Name) and sub.id in mod_dead:
                return True
            if isinstance(sub, ast.Attribute) and hits(_attr_chain(sub), dead):
                return True
        return False

    cut: list[tuple[int, int]] = []
    keep_uses = False
    for n in tree.body:
        start = min([n.lineno] + [d.lineno for d in getattr(n, "decorator_list", [])])
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            named = n.name in gone
            args = {a.arg for a in n.args.args} if not isinstance(n, ast.ClassDef) else set()
            if named or uses_dead(n) or args & gone:
                cut.append((start, n.end_lineno))
                gone.add(n.name)
        elif isinstance(n, (ast.Import, ast.ImportFrom)):
            if _dead_names(n, dead):
                if isinstance(n, ast.ImportFrom) and any(
                        (a.asname or a.name) not in _dead_names(n, dead) for a in n.names):
                    keep_uses = True  # mixed import: leave it, the check below drops the file
                else:
                    cut.append((start, n.end_lineno))
        elif uses_dead(n):
            keep_uses = True
    if keep_uses:
        path.unlink()
        return
    if not cut:
        return
    for a, b in sorted(cut, reverse=True):
        del lines[a - 1:b]
    path.write_text("".join(lines))
    remaining = ast.parse(path.read_text())
    if path.name.startswith("test_") and not any(
            isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test")
            or isinstance(n, ast.ClassDef) for n in remaining.body):
        path.unlink()


def _attr_chain(n: ast.Attribute) -> set[str]:
    parts, cur = [], n
    while isinstance(cur, ast.Attribute):
        parts.append(cur.attr)
        cur = cur.value
    if isinstance(cur, ast.Name):
        parts.append(cur.id)
    parts.reverse()
    return {".".join(parts[:i]) for i in range(1, len(parts) + 1)}


def apply(out: Path) -> None:
    (out / "py").mkdir()
    shutil.move(out / "src/stockpilot", out / "py/stockpilot")
    shutil.rmtree(out / "src")
    shutil.move(out / "tests", out / "py/tests")
    shutil.move(out / "pyproject.toml", out / "py/pyproject.toml")
    shutil.move(out / "uv.lock", out / "py/uv.lock")

    legacy = out / "legacy"
    (legacy / "workflows").mkdir(parents=True)
    for wf in sorted((out / ".github/workflows").glob("*.yml")):
        if wf.name not in WORKFLOWS_KEEP:
            shutil.move(wf, legacy / "workflows" / wf.name)
    shutil.move(out / "web", legacy / "web")

    pkg, tests = out / "py/stockpilot", out / "py/tests"
    for m in DELETE_MODULES:
        for p in mod_path(pkg, m):
            rm(p)
    for t in DELETE_TESTS:
        for p in mod_path(tests, t[:-3] if t.endswith(".py") else t) or [tests / t]:
            if p.exists():
                rm(p)
    # tests that exercise a deleted module go with it: whole test functions are cut, a file goes only
    # when what is left still needs the deleted module
    dead = {dotted(m) for m in DELETE_MODULES}
    conf_gone: dict[Path, set[str]] = {}      # fixtures cut from a conftest.py, by its folder
    for t in sorted(tests.rglob("*.py"), key=lambda f: (f.name != "conftest.py", str(f))):
        gone = set(DELETE_TEST_FUNCS)
        for folder, names in conf_gone.items():
            if folder in t.parents:
                gone |= names
        for _ in range(3):       # a cut fixture takes its tests with it
            if t.exists():
                prune_test(t, dead, gone)
        if t.name == "conftest.py":
            conf_gone[t.parent] = gone - set(DELETE_TEST_FUNCS)
    for d in sorted(tests.rglob("*"), reverse=True):
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    # surviving code must not import anything deleted
    for p in sorted(pkg.rglob("*.py")):
        if hits(imports(p), dead):
            sys.exit(f"{p.relative_to(out)} still imports a deleted module")

    # tests sit one level deeper (py/tests): the repo root is one level further up
    # (py/stockpilot is as deep as src/stockpilot was, so the package needs no change)
    for f in tests.rglob("*.py"):
        t = f.read_text()
        n = re.sub(r"(\b_?[Rr][Oo][Oo][Tt]\b *= *Path\(__file__\)(?:\.resolve\(\))?\.parents\[)(\d)\]",
                   lambda m: f"{m[1]}{int(m[2]) + 1}]", t)
        n = re.sub(r"(\b_?[Rr][Oo][Oo][Tt]\b *= *Path\(__file__\)\.parent\.parent)\b(?!\.parent)", r"\1.parent", n)
        n = re.sub(r"(Path\(__file__\)(?:\.resolve\(\))?\.parents\[)(\d)(\] / \"(?:schemas|config|web|prompts|docs|\.github)\")",
                   lambda m: f"{m[1]}{int(m[2]) + 1}{m[3]}", n)
        n = n.replace('ROOT = __import__("pathlib").Path(__file__).resolve().parents[2]',
                      'ROOT = __import__("pathlib").Path(__file__).resolve().parents[3]')
        n = n.replace('.parents[2] / "src" / "stockpilot"', '.parents[2] / "stockpilot"')
        # what moved: v2 web/ and the v2 workflows are under legacy/, the package under py/
        for a, b in (('"web" / "migrations"', '"legacy" / "web" / "migrations"'),
                     ('(ROOT / "web/functions")', '(ROOT / "legacy/web/functions")'),
                     ('(ROOT / "web/lib")', '(ROOT / "legacy/web/lib")'),
                     ('ROOT / "src/stockpilot/sources/kite.py"', 'ROOT / "py/stockpilot/sources/kite.py"'),
                     ('".github" / "workflows"', '"legacy" / "workflows"')):
            n = n.replace(a, b)
        if n != t:
            f.write_text(n)

    pp = out / "py/pyproject.toml"
    s = pp.read_text()
    s = s.replace('[project.scripts]\nsp = "stockpilot.cli:main"\n\n', "")
    s = s.replace('packages = ["src/stockpilot"]', 'packages = ["stockpilot"]')
    s = s.replace('    "reportlab>=5.1.0",\n', '    "reportlab>=5.1.0",\n    "pytest-xdist>=3.6",\n')
    pp.write_text(s)

    subprocess.run(["uv", "lock", "--project", str(out / "py")], check=True)   # the lock gains pytest-xdist

    # pnpm workspace shells, shared config, CI
    for f in ("package.json", "pnpm-workspace.yaml", "biome.json", "tsconfig.base.json", ".nvmrc", ".gitignore"):
        src = TEMPLATES / f
        shutil.copy(src if src.exists() else TEMPLATES / f"{f}.tmpl", out / f)   # biome.json.tmpl: Biome must not see it as a nested root
    for ws in ("contract", "money", "api", "web", "adapters"):
        d = out / ws
        (d / "src").mkdir(parents=True)
        (d / "src/index.ts").write_text("export {};\n")
        (d / "package.json").write_text(
            '{\n  "name": "@stockpilot/%s",\n  "version": "0.0.0",\n  "private": true,\n  "type": "module",\n'
            '  "scripts": {\n    "test": "vitest run --passWithNoTests",\n    "typecheck": "tsc --noEmit"\n  }\n}\n' % ws)
        (d / "tsconfig.json").write_text(
            '{\n  "extends": "../tsconfig.base.json",\n  "include": ["src"]\n}\n')
    shutil.copy(TEMPLATES / "ci.yml", out / ".github/workflows/ci.yml")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="b3b3010")
    ap.add_argument("--out")
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    if a.check:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            out.mkdir()
            export(a.base, out)
            apply(out)
            r = subprocess.run(["diff", "-rq", str(out), ".", "-x", ".git", "-x", "tools", "-x", "checks",
                                "-x", ".claude", "-x", "node_modules", "-x", ".venv", "-x", "pnpm-lock.yaml", "-x", "uv.lock",   # the locks resolve per machine: not compared
                                "-x", "__pycache__", "-x", ".pytest_cache", "-x", ".ruff_cache"],
                               capture_output=True, text=True)
            only_out = [l for l in r.stdout.splitlines() if l.startswith("Only in " + str(out))]
            diffs = [l for l in r.stdout.splitlines() if l.startswith("Files ")]
            print("\n".join(only_out + diffs) or "layout matches")
            sys.exit(1 if only_out or diffs else 0)
    out = Path(a.out)
    if out.exists() and any(out.iterdir()):
        sys.exit(f"{out} is not empty")
    out.mkdir(parents=True, exist_ok=True)
    export(a.base, out)
    apply(out)
    print(f"built {out}")


if __name__ == "__main__":
    main()
