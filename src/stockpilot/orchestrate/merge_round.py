"""One orchestrator merge round: merge every green lane at once, never wait.

A lane reports `DONE <branch> <sha> pytest=<p>/<f> e2e=<pass|fail>`. The round
merges each green lane in order and skips the rest with a reason. It never
sleeps; the caller runs it the moment a DONE arrives.
"""
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

_DONE = re.compile(
    r"^DONE\s+(?P<branch>\S+)\s+(?P<sha>[0-9a-f]{7,40})\s+"
    r"pytest=(?P<p>\d+)/(?P<f>\d+)\s+e2e=(?P<e2e>pass|fail|na)\s*$")


@dataclass(frozen=True)
class Done:
    branch: str
    sha: str
    passed: int
    failed: int
    e2e: str

    @property
    def green(self) -> bool:
        return self.failed == 0 and self.e2e != "fail"


@dataclass(frozen=True)
class Skipped:
    branch: str
    reason: str


@dataclass
class RoundResult:
    merged: list[Done] = field(default_factory=list)
    skipped: list[Skipped] = field(default_factory=list)


def parse_done(line: str) -> Done | None:
    m = _DONE.match(line.strip())
    if not m:
        return None
    return Done(m["branch"], m["sha"], int(m["p"]), int(m["f"]), m["e2e"])


def _git(repo, *args, check=True):
    return subprocess.run(["git", "-C", str(repo), *args], check=check,
                          capture_output=True, text=True)


def merge_round(repo: str | Path, dones: list[Done], base: str = "main",
                dry_run: bool = False) -> RoundResult:
    """Merge green, unmoved, conflict-free lanes into `base`, in the order given.

    dry_run runs the same merges on a throwaway branch and leaves `base` as is.
    """
    result = RoundResult()
    start = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    work = base
    if dry_run:
        work = "dryrun/merge-round"
        _git(repo, "branch", "-f", work, base)
    _git(repo, "switch", work)
    try:
        for d in dones:
            if not d.green:
                result.skipped.append(Skipped(d.branch, "tests red"))
                continue
            head = _git(repo, "rev-parse", d.branch, check=False)
            if head.returncode or not head.stdout.strip().startswith(d.sha):
                result.skipped.append(Skipped(d.branch, "head moved since DONE"))
                continue
            merge = _git(repo, "merge", "--no-ff", "-m", f"Merge {d.branch}",
                         d.branch, check=False)
            if merge.returncode:
                _git(repo, "merge", "--abort", check=False)
                result.skipped.append(Skipped(d.branch, "merge conflict"))
                continue
            result.merged.append(d)
    finally:
        _git(repo, "switch", start)
        if dry_run:
            _git(repo, "branch", "-D", work)
    return result
