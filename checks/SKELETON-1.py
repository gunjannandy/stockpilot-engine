"""SKELETON-1: the generators run in CI and their output is git-ignored."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = [
    "contract/src/index.ts",
    "contract/generated/schemas/dataset.ping.schema.json",
    "contract/generated/manifest.json",
    "web/src/generated/client.ts",
]


def test_gen_builds_every_output_and_git_ignores_it():
    subprocess.run(["pnpm", "gen"], cwd=ROOT, check=True, capture_output=True)
    for rel in OUTPUT:
        assert (ROOT / rel).is_file(), rel
        assert subprocess.run(["git", "check-ignore", "-q", rel], cwd=ROOT).returncode == 0, f"{rel} is not git-ignored"
        assert subprocess.run(["git", "ls-files", "--error-unmatch", rel], cwd=ROOT, capture_output=True).returncode != 0, f"{rel} is tracked"


def test_ci_runs_the_generators_before_python_and_typescript_read_them():
    ci = (ROOT / ".github/workflows/ci.yml").read_text()
    pkg = (ROOT / "package.json").read_text()
    py_job = ci.split("\n  py:")[1].split("\n  ts:")[0]
    assert "pnpm gen" in py_job, "the py job reads the generated JSON Schemas"
    assert re.search(r'"typecheck": "pnpm gen', pkg) and re.search(r'"test": "pnpm gen', pkg), "the ts job's typecheck and test run gen first"


def test_parallel_gen_runs_do_not_delete_each_others_output():
    """pytest-xdist workers call `pnpm gen` together; every run must succeed and the output must always be whole."""
    procs = [subprocess.Popen(["pnpm", "gen"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for _ in range(6)]
    results = [(p.communicate()[0], p.returncode) for p in procs]
    for out, code in results:
        assert code == 0, out
    for rel in OUTPUT:
        assert (ROOT / rel).is_file(), rel
