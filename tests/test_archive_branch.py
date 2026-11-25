"""R16: the first ship creates the `archive` branch (it does not exist yet) as an orphan, with no force push, and never touches
main or a stage branch."""
import json
import subprocess
from datetime import date, datetime

import pytest

from fakes import make_machine
from seed_site import seed as seed_site
from stockpilot import ops
from stockpilot.jobs import ship


def git(*args, cwd=None):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _remote_with_branches(tmp_path, branches=("main", "stage-1-skeleton", "feature/archive")):
    """A bare remote that already holds real work on other branches, each with its own history."""
    bare = tmp_path / "remote.git"
    git("init", "-q", "--bare", str(bare))
    work = tmp_path / "work"
    git("init", "-q", "-b", branches[0] if branches else "main", str(work))
    for i, name in enumerate(branches):
        git("checkout", "-q", "-B", name, cwd=work) if i else None
        (work / f"{i}.txt").write_text(name)
        git("add", ".", cwd=work)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", f"work on {name}", cwd=work)
        git("push", "-q", str(bare), f"{name}:{name}", cwd=work)
    return str(bare)


def _heads(remote):
    out = git("--git-dir", remote, "for-each-ref", "--format=%(refname:short) %(objectname)", "refs/heads")
    return dict(line.split() for line in out.splitlines())


def _ship(tmp_path, remote, day=date(2026, 11, 20)):
    seed_site(tmp_path / "data" / "stockpilot.duckdb").close()
    m = make_machine(tmp_path, now=datetime(2026, 11, 22, 23, 33),
                     push_archive=lambda d, payload: ops.archive_push(remote, d, payload))
    with m.db("ship") as db:
        return ship.ship(m, db, datetime.combine(day, datetime.min.time().replace(hour=20)))


def test_the_first_ship_creates_archive_as_an_orphan_and_leaves_other_branches_alone(tmp_path):
    remote = _remote_with_branches(tmp_path)
    before = _heads(remote)
    assert "archive" not in before
    out = _ship(tmp_path, remote)
    assert "archive" not in out, out                      # no "failed" note from the push
    after = _heads(remote)
    assert set(after) == set(before) | {"archive"}
    assert {k: after[k] for k in before} == before        # main, the stage branch and feature/archive: same commits
    roots = git("--git-dir", remote, "rev-list", "--max-parents=0", "archive").split()
    assert len(roots) == 1 and roots[0] not in git("--git-dir", remote, "rev-list", "--all", "--not", "archive").split()
    shared = subprocess.run(["git", "--git-dir", remote, "merge-base", "archive", "main"], capture_output=True, text=True)
    assert shared.returncode == 1                         # no common history: an orphan
    assert json.loads(git("--git-dir", remote, "show", "archive:2026-11-20/calls.json"))


def test_a_branch_whose_name_ends_in_archive_is_not_taken_for_the_archive(tmp_path):
    remote = _remote_with_branches(tmp_path, ("main", "feature/archive"))
    ops.archive_push(remote, date(2026, 11, 20), {"calls": [{"symbol": "AAA"}], "brief": None})
    heads = _heads(remote)
    assert "archive" in heads and heads["archive"] != heads["feature/archive"]


def test_an_empty_remote_gets_an_archive_branch(tmp_path):
    bare = tmp_path / "empty.git"
    git("init", "-q", "--bare", str(bare))
    assert ops.archive_push(str(bare), date(2026, 11, 20), {"calls": [{"symbol": "AAA"}], "brief": None}) is True
    assert set(_heads(str(bare))) == {"archive"}


def test_a_second_ship_appends_on_top_and_never_rewrites(tmp_path):
    remote = _remote_with_branches(tmp_path)
    _ship(tmp_path, remote, date(2026, 11, 20))
    first = _heads(remote)["archive"]
    ops.archive_push(remote, date(2026, 11, 23), {"calls": [{"symbol": "BBB"}], "brief": None})
    assert git("--git-dir", remote, "merge-base", "--is-ancestor", first, "archive") == ""      # raises if not an ancestor
    assert len(git("--git-dir", remote, "rev-list", "archive").split()) == 2


def test_it_will_not_push_to_main_or_a_stage_branch_whatever_the_name_passed(tmp_path):
    remote = _remote_with_branches(tmp_path)
    before = _heads(remote)
    for name in ("main", "master", "stage-1-skeleton", "status", "vault"):
        with pytest.raises(ValueError):
            ops.archive_push(remote, date(2026, 11, 20), {"calls": [{"symbol": "A"}], "brief": None}, branch=name)
    assert _heads(remote) == before


def test_a_racing_creator_is_never_forced_over(tmp_path, monkeypatch):
    """Another machine made `archive` between our look and our push: the push is refused, the other history stays."""
    remote = _remote_with_branches(tmp_path)
    other = tmp_path / "other"
    git("init", "-q", "-b", "archive", str(other))
    (other / "x").write_text("theirs")
    git("add", ".", cwd=other)
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "-m", "theirs", cwd=other)
    git("push", "-q", remote, "archive:archive", cwd=other)
    theirs = _heads(remote)["archive"]
    monkeypatch.setattr(ops, "_has_branch", lambda r, b: False)
    with pytest.raises(subprocess.CalledProcessError):
        ops.archive_push(remote, date(2026, 11, 20), {"calls": [{"symbol": "A"}], "brief": None})
    assert _heads(remote)["archive"] == theirs
