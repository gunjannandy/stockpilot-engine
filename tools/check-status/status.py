"""Derive checks/status.json: a check is `passed` once its file is on main (main only takes green PRs), else `pending`.

CI writes the result as a build artifact; nothing commits it.
Usage: python tools/check-status/status.py [--main-ref origin/main] [--out checks/status.json]
"""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from gates import trace  # noqa: E402


def derive(rows, main_files):
    on_main = {Path(p).stem for p in main_files if p.startswith("checks/")}
    return {r["check_id"]: ("passed" if r["check_id"] in on_main else "pending") for r in rows}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--main-ref", default="origin/main")
    ap.add_argument("--out", default=str(ROOT / "checks/status.json"))
    a = ap.parse_args(argv)
    r = subprocess.run(["git", "ls-tree", "-r", "--name-only", a.main_ref, "checks/"], cwd=ROOT, capture_output=True, text=True)
    main_files = r.stdout.split() if r.returncode == 0 else []
    rows = trace.parse((ROOT / "checks/trace.csv").read_text())
    Path(a.out).write_text(json.dumps(derive(rows, main_files), indent=1, sort_keys=True) + "\n")


if __name__ == "__main__":
    main()
