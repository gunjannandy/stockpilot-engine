import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "ops/orchestrator/tests"))
from orch_helpers import *  # noqa: E402,F401,F403
import dispatch  # noqa: E402
import pace  # noqa: E402
import buildstatus  # noqa: E402


def test_a_ticket_with_no_owned_paths_runs_alone():
    bare = ticket(1, "BARE", owns=[])
    other = ticket(2, "O", owns=["o/**"])
    plan = dispatch.plan(world([bare, other]))
    assert [c["ticket"] for c in plan["claims"]] == ["O"], "tickets that declare paths go first; the bare one waits"
    alone = dispatch.plan(world([bare]))
    assert [c["ticket"] for c in alone["claims"]] == ["BARE"]


def test_bare_ticket_waits_while_anything_runs_and_blocks_others_while_it_runs():
    bare = ticket(1, "BARE", owns=[])
    busy = ticket(2, "BUSY", owns=["o/**"], claims=[claim("primary", 10)])
    assert dispatch.plan(world([bare, busy]))["claims"] == []
    running_bare = ticket(1, "BARE", owns=[], claims=[claim("primary", 10)])
    other = ticket(2, "O", owns=["o/**"])
    assert dispatch.plan(world([running_bare, other]))["claims"] == []


def test_once_the_claim_comment_declares_paths_others_may_run_beside_it():
    declared = ticket(1, "BARE", owns=["b/**"], claims=[claim("primary", 10)])
    other = ticket(2, "O", owns=["o/**"])
    assert keys(dispatch.plan(world([declared, other]))["claims"], "ticket") == ["O"]


def test_gather_reads_declared_paths_and_checks_from_a_claim_comment():
    import gather
    c = "Claimed by secondary: s1\nOwned paths:\n- `b/**`\n- `c/x.py`\nChecks:\n- `C-1-1` (unit): thing\n"
    assert gather.parse_claim_declaration(c) == {"owns": ["b/**", "c/x.py"], "checks": ["C-1-1"]}
    assert gather.parse_claim_declaration("Claimed by secondary: s1") == {"owns": [], "checks": []}
