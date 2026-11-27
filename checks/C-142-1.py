"""C-142-1: a PR touching workflows, tools/gates or a passed check fails unless stockpilot-bot added the planner label."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from gates import planner_label as pl  # noqa: E402

BOT = {"login": "stockpilot-bot[bot]"}
HUMAN = {"login": "gunjannandy"}


def ev(kind, actor, label="planner"):
    return {"event": kind, "actor": actor, "label": {"name": label}}


def test_protected_paths_need_the_label():
    for path in (".github/workflows/ci.yml", ".github/workflows/x/y.yml", "tools/gates/privacy.py", "checks/C-001-1.py"):
        assert pl.needs_label([path], main_files=["checks/C-001-1.py"]), path


def test_other_paths_and_new_checks_do_not():
    assert not pl.needs_label(["py/x.py", "tools/check-status/s.py", "checks/C-009-9.py", "checks/trace.csv"], main_files=["checks/C-001-1.py", "checks/trace.csv"])


def test_label_by_the_bot_passes():
    assert pl.verdict([".github/workflows/ci.yml"], [], [ev("labeled", BOT)]) == []


def test_label_by_anyone_else_or_none_fails():
    assert pl.verdict([".github/workflows/ci.yml"], [], [ev("labeled", HUMAN)])
    assert pl.verdict([".github/workflows/ci.yml"], [], [])
    assert pl.verdict([".github/workflows/ci.yml"], [], [ev("labeled", BOT, "other")])


def test_a_label_the_bot_added_then_anyone_removed_or_re_added_by_a_human_fails():
    assert pl.verdict(["tools/gates/a.py"], [], [ev("labeled", BOT), ev("unlabeled", HUMAN)])
    assert pl.verdict(["tools/gates/a.py"], [], [ev("labeled", BOT), ev("unlabeled", HUMAN), ev("labeled", HUMAN)])
    assert pl.verdict(["tools/gates/a.py"], [], [ev("labeled", HUMAN), ev("unlabeled", HUMAN), ev("labeled", BOT)]) == []


def test_untouched_protected_paths_need_nothing():
    assert pl.verdict(["py/x.py"], [], []) == []
