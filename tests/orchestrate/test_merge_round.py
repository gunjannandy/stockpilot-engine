"""Dry run of an orchestrator merge round with two fake lanes."""
import subprocess
import time

import pytest

from stockpilot.orchestrate import merge_round as mr


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "repo"
    r.mkdir()
    git(r, "init", "-b", "main")
    git(r, "config", "user.email", "t@example.com")
    git(r, "config", "user.name", "t")
    (r / "base.txt").write_text("base\n")
    git(r, "add", "-A"); git(r, "commit", "-m", "base")
    for name in ("T1", "T2"):
        git(r, "switch", "-c", f"lane/{name}", "main")
        (r / f"{name}.txt").write_text(name)
        git(r, "add", "-A"); git(r, "commit", "-m", name)
        git(r, "switch", "main")
    return r


def sha(r, b):
    return git(r, "rev-parse", b)


def test_parse_done_line():
    d = mr.parse_done("DONE lane/T1 abc1234 pytest=12/0 e2e=pass")
    assert (d.branch, d.sha, d.passed, d.failed, d.e2e) == ("lane/T1", "abc1234", 12, 0, "pass")
    assert mr.parse_done("working on it") is None


def test_two_green_lanes_merge_with_no_wait(repo, monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda *_: pytest.fail("round must not sleep"))
    dones = [mr.parse_done(f"DONE lane/{n} {sha(repo, f'lane/{n}')} pytest=5/0 e2e=pass")
             for n in ("T1", "T2")]
    result = mr.merge_round(repo, dones, base="main")
    assert [m.branch for m in result.merged] == ["lane/T1", "lane/T2"]
    assert result.skipped == []
    assert (repo / "T1.txt").exists() and (repo / "T2.txt").exists()


def test_dry_run_leaves_main_untouched(repo):
    before = sha(repo, "main")
    dones = [mr.parse_done(f"DONE lane/{n} {sha(repo, f'lane/{n}')} pytest=5/0 e2e=pass")
             for n in ("T1", "T2")]
    result = mr.merge_round(repo, dones, base="main", dry_run=True)
    assert [m.branch for m in result.merged] == ["lane/T1", "lane/T2"]
    assert sha(repo, "main") == before


def test_red_or_stale_lane_is_skipped_not_merged(repo):
    red = mr.parse_done(f"DONE lane/T1 {sha(repo, 'lane/T1')} pytest=5/1 e2e=pass")
    stale = mr.parse_done("DONE lane/T2 0000000 pytest=5/0 e2e=pass")
    result = mr.merge_round(repo, [red, stale], base="main")
    assert result.merged == []
    assert {s.branch: s.reason for s in result.skipped} == {
        "lane/T1": "tests red", "lane/T2": "head moved since DONE"}
    assert not (repo / "T1.txt").exists()


def test_conflicting_lane_is_aborted_and_next_still_merges(repo):
    git(repo, "switch", "lane/T1"); (repo / "x.txt").write_text("one")
    git(repo, "add", "-A"); git(repo, "commit", "-m", "x1")
    git(repo, "switch", "-c", "lane/T3", "main"); (repo / "x.txt").write_text("three")
    git(repo, "add", "-A"); git(repo, "commit", "-m", "x3"); git(repo, "switch", "main")
    dones = [mr.parse_done(f"DONE lane/{n} {sha(repo, f'lane/{n}')} pytest=1/0 e2e=pass")
             for n in ("T1", "T3", "T2")]
    result = mr.merge_round(repo, dones, base="main")
    assert [m.branch for m in result.merged] == ["lane/T1", "lane/T2"]
    assert result.skipped[0].branch == "lane/T3" and result.skipped[0].reason == "merge conflict"
    assert git(repo, "status", "--porcelain") == ""


def test_e2e_na_counts_as_green():
    assert mr.parse_done("DONE lane/T9 abc1234 pytest=3/0 e2e=na").green
    assert not mr.parse_done("DONE lane/T9 abc1234 pytest=3/0 e2e=fail").green
