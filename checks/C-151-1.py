import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops/orchestrator/tests"))
from orch_helpers import *  # noqa: E402,F401,F403
import dispatch  # noqa: E402
import pace  # noqa: E402
import buildstatus  # noqa: E402


def test_ready_tickets_with_disjoint_files_are_claimed_once_per_account():
    a = ticket(1, "A", owns=["x/**"])
    b = ticket(2, "B", owns=["y/**", "contract/**"])
    c = ticket(3, "C", owns=["x/sub/file.py"])            # overlaps A
    d = ticket(4, "D", owns=["contract/**", "z/**"])      # contract is shared
    blocked = ticket(5, "E", owns=["q/**"], blocked_by=[1])
    vm = ticket(6, "VM1", owns=["v/**"], labels=["ready-for-agent", "v3-vm"], vm=True)
    plan = dispatch.plan(world([a, b, c, d, blocked, vm]))
    assert keys(plan["claims"], "ticket") == ["A", "B", "D"]
    assert all(c["account"] == "secondary" for c in plan["claims"])
    already = ticket(1, "A", owns=["x/**"], claims=[claim("secondary", 5)], labels=["ready-for-agent", "pool:secondary"])
    plan2 = dispatch.plan(world([already]))
    assert plan2["claims"] == [], "a ticket this account has claimed is not claimed again"


def test_a_running_tickets_files_block_overlapping_claims():
    running = ticket(1, "R", owns=["x/**"], claims=[claim("primary", 30)])
    other = ticket(2, "O", owns=["x/a.py"])
    assert dispatch.plan(world([running, other]))["claims"] == []


def test_critical_path_first_then_most_unblocking():
    a = ticket(1, "A", owns=["a/**"])
    b = ticket(2, "B", owns=["b/**"], critical=True)
    c = ticket(3, "C", owns=["c/**"])
    d1 = ticket(4, "D1", owns=["d1/**"], blocked_by=[3])
    d2 = ticket(5, "D2", owns=["d2/**"], blocked_by=[3])
    d3 = ticket(6, "D3", owns=["d3/**"], blocked_by=[1])
    order = [c["ticket"] for c in dispatch.plan(world([a, b, c, d1, d2, d3]))["claims"]]
    assert order == ["B", "C", "A"]


def test_ui_tickets_start_on_the_driver_only():
    ui = ticket(1, "U", ui=True, labels=["v3-ui", "ready-for-agent"])
    assert dispatch.plan(world([ui], account="secondary"))["claims"] == []
    assert keys(dispatch.plan(world([ui], account="primary"))["claims"], "ticket") == ["U"]


def test_claiming_plans_a_builder_on_a_lane_branch_with_the_private_repo_as_source():
    plan = dispatch.plan(world([ticket(1, "A")]))
    s = plan["start"][0]
    assert (s["ticket"], s["branch"], s["model"], s["permission_mode"], s["source"], s["reason"]) == \
        ("A", "lane/A", "sonnet", "auto", "stockpilot-hq/stockpilot", "new_claim")
    assert s["prompt"] == "Build issue #1"
