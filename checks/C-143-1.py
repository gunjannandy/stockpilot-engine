"""C-143-1: a story with no check fails; a changed passed check without the planner label fails."""
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from gates import planner_label as pl, trace  # noqa: E402

spec = importlib.util.spec_from_file_location("check_status", ROOT / "tools/check-status/status.py")
status = importlib.util.module_from_spec(spec)
spec.loader.exec_module(status)

HEADER = "story,check_id,ticket,kind,what\n"


def test_a_story_with_no_check_fails():
    assert trace.check_text(HEADER + "1,C-001-1,A,unit,x\n2,,A,unit,y\n")
    assert trace.check_text(HEADER + "1,C-001-1,A,unit,x\n1,C-001-1,A,unit,dupe\n")
    assert trace.check_text(HEADER + "1,not-an-id,A,unit,x\n")


def test_a_complete_map_passes_and_this_repos_trace_is_complete():
    assert trace.check_text(HEADER + '1,C-001-1,A,unit,"x, y"\n1,C-001-2,A,unit,z\n') == []
    assert trace.check_text((ROOT / "checks/trace.csv").read_text()) == []


def test_a_changed_passed_check_without_the_label_fails():
    assert pl.verdict(["checks/C-001-1.py"], ["checks/C-001-1.py"], [])
    assert pl.verdict(["checks/C-001-1.py"], ["checks/C-001-1.py"], [{"event": "labeled", "actor": {"login": "stockpilot-bot[bot]"}, "label": {"name": "planner"}}]) == []


def test_status_is_pending_until_the_check_file_is_on_main():
    rows = trace.parse(HEADER + "1,C-001-1,A,unit,x\n2,C-002-1,A,unit,y\n")
    got = status.derive(rows, main_files=["checks/C-001-1.py", "checks/trace.csv"])
    assert got["C-001-1"] == "passed" and got["C-002-1"] == "pending"
    assert status.derive(rows, main_files=[]) == {"C-001-1": "pending", "C-002-1": "pending"}
