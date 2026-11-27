"""Never-order gate: any broker order-writing endpoint anywhere in the repo fails. Read endpoints pass."""
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

PATTERNS = [
    ("order-call", re.compile(r"\b(?:place|modify|cancel|exit)_?(?:regular_|amo_|co_|iceberg_|auction_)?order\b", re.I)),
    ("order-path", re.compile(r"/orders?/(?:regular|amo|co|iceberg|auction|place|modify|cancel)\b", re.I)),
    ("gtt", re.compile(r"\b(?:place|modify|delete)_?gtt\b|\b(?:POST|PUT|DELETE)\b[^\n]{0,40}/gtt" r"/triggers", re.I)),
    ("convert-position", re.compile(r"\bconvert_?position\b", re.I)),
]
MAX_BYTES = 2_000_000
# Lines that name an order call only to prove it is banned (a test asserting its absence). Each entry is
# "path<TAB>stripped line"; the file sits in tools/gates, so changing it needs the planner label.
ALLOW_FILE = Path(__file__).with_name("never_order_allow.txt")


def _allowed():
    if not ALLOW_FILE.is_file():
        return set()
    return {ln for ln in ALLOW_FILE.read_text().splitlines() if ln and not ln.startswith("#")}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str

    def __str__(self):
        return f"{self.path}:{self.line}: {self.rule}"


def tracked_files(root):
    out = subprocess.run(["git", "ls-files", "-z"], cwd=root, check=True, capture_output=True).stdout
    return [p for p in out.decode().split("\0") if p]


def scan_files(root, paths):
    root, found, allowed = Path(root), [], _allowed()
    for rel in paths:
        p = root / rel
        if not p.is_file() or p.stat().st_size > MAX_BYTES or p.resolve() == ALLOW_FILE.resolve():
            continue
        raw = p.read_bytes()
        if b"\0" in raw:
            continue
        for n, line in enumerate(raw.decode("utf-8", "replace").splitlines(), 1):
            if f"{rel}\t{line.strip()}" in allowed:
                continue
            for rule, rx in PATTERNS:
                if rx.search(line):
                    found.append(Finding(rel, n, rule))
    return found
