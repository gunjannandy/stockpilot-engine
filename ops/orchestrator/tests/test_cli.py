import json
import subprocess
import sys

from orch_helpers import ORCH, ticket, world


def test_cli_prints_the_plan_as_json(tmp_path):
    f = tmp_path / "in.json"
    f.write_text(json.dumps(world([ticket(1, "A")])))
    out = subprocess.run([sys.executable, str(ORCH / "dispatch.py"), "--account", "secondary", "--inputs", str(f)],
                         capture_output=True, text=True, check=True).stdout
    plan = json.loads(out)
    assert plan["account"] == "secondary" and plan["claims"][0]["ticket"] == "A"


def test_gather_builds_a_ticket_from_an_issue_and_its_comments():
    import gather
    body = ("## Parent\n\nPart of #133. Key `ZED`.\n\nBlocked by: #134, #135\n\n## Acceptance criteria\n\n"
            "- [ ] `C-1-1` (unit): a\n- [x] `C-1-2` (unit): b\n\n## Owned paths\n\n- `z/**`\n- `y/a.py`\n\n## How to work\n")
    issue = {"number": 7, "title": "t", "body": body, "labels": [{"name": "v3-ui"}, {"name": "ready-for-agent"}]}
    comments = [{"body": "Claimed by secondary: s1", "created_at": "2026-12-01T09:00:00Z"},
                {"body": "Claimed by primary: s2", "created_at": "2026-12-01T09:01:00Z"},
                {"body": "Withdrawn by primary: s2", "created_at": "2026-12-01T09:02:00Z"},
                {"body": "Replaced stuck builder (1/3)", "created_at": "2026-12-01T09:03:00Z"}]
    t = gather.build_ticket(issue, comments)
    assert (t["key"], t["blocked_by"], t["owns"], t["unticked"], t["ui"], t["stuck_count"]) == \
        ("ZED", [134, 135], ["z/**", "y/a.py"], ["C-1-1"], True, 1)
    assert [c["account"] for c in t["claims"]] == ["secondary"]


def test_check_state_reads_check_runs_never_prose():
    import gather
    assert gather.check_state([{"conclusion": "success"}]) == "green"
    assert gather.check_state([{"conclusion": "success"}, {"conclusion": "failure"}]) == "red"
    assert gather.check_state([{"conclusion": None}]) == "pending"
    assert gather.check_state([]) == "none"
