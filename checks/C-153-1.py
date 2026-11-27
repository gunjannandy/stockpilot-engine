import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops/orchestrator/tests"))
from orch_helpers import *  # noqa: E402,F401,F403
import dispatch  # noqa: E402
import pace  # noqa: E402
import buildstatus  # noqa: E402


def test_builder_that_stopped_with_unticked_checks_is_resumed_naming_them():
    t = ticket(1, "A", claims=[claim("secondary", 300)], unticked=["C-9-1", "C-9-2"])
    p = dispatch.plan(world([t], [session("s1", "A", status="idle", last_event=5)]))
    r = p["resume"][0]
    assert "C-9-1" in r["message"] and "C-9-2" in r["message"]


def test_idle_with_every_check_ticked_and_a_green_pr_is_left_alone():
    t = ticket(1, "A", claims=[claim("secondary", 300)], pr={"number": 9, "state": "open", "ci": "green"})
    p = dispatch.plan(world([t], [session("s1", "A", status="idle", last_event=500)]))
    assert p["resume"] == [] and p["nudge"] == []


def test_left_over_line_outside_owned_paths_becomes_a_ticket_once():
    t = ticket(1, "A", owns=["a/**"], claims=[claim("secondary", 300)])
    lo = [{"ticket": "A", "line": "wire the thing in `b/x.py`", "files": ["b/x.py"]},
          {"ticket": "A", "line": "tidy `a/y.py`", "files": ["a/y.py"]},
          {"ticket": "A", "line": "none", "files": []}]
    p = dispatch.plan(world([t], left_over=lo))
    assert len(p["new_tickets"]) == 1
    n = p["new_tickets"][0]
    assert "ready-for-agent" in n["labels"] and "b/x.py" in n["body"] and n["from"] == "A"
    again = dispatch.plan(world([t], left_over=lo, known_left_over=[n["id"]]))
    assert again["new_tickets"] == []
    assert [w["line"] for w in p["warnings"]] == ["tidy `a/y.py`"]


def test_parse_left_over_block_from_a_pr_body():
    import gather
    body = "Refs x\n\nLeft over:\n- wire `b/x.py` and `b/z/**`\n- none\n"
    assert gather.parse_left_over(body) == [{"line": "wire `b/x.py` and `b/z/**`", "files": ["b/x.py", "b/z/**"]}]
    assert gather.parse_left_over("Left over:\n- none") == []
    assert gather.parse_left_over("no block here") == []
