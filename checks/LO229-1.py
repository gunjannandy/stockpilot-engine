"""LO229: `pnpm gen` is safe to run in parallel (pytest-xdist workers call it together)."""
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = [
    "contract/src/index.ts",
    "contract/generated/schemas/dataset.ping.schema.json",
    "contract/generated/manifest.json",
    "web/src/generated/client.ts",
]


def test_parallel_gen_runs_do_not_delete_each_others_output():
    procs = [subprocess.Popen(["pnpm", "gen"], cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True) for _ in range(6)]
    results = [(p.communicate()[0], p.returncode) for p in procs]
    for out, code in results:
        assert code == 0, out
    for rel in OUTPUT:
        assert (ROOT / rel).is_file(), rel
