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


def test_collect_reads_issues_comments_prs_and_check_runs_through_the_api():
    import gather
    body = "Key `ZED`.\n\n## Owned paths\n\n- `z/**`\n"
    issues = [{"number": 7, "title": "t", "body": body, "labels": [{"name": "v3-wave-0"}]},
              {"number": 8, "title": "pr", "body": "", "labels": [{"name": "v3-wave-0"}], "pull_request": {}},
              {"number": 9, "title": "other", "body": "", "labels": [{"name": "bug"}]}]

    def api(path, *a):
        if path.endswith("/issues"):
            return issues
        if path.endswith("/comments"):
            return [{"body": "Claimed by secondary: s1", "created_at": "2026-12-01T09:00:00Z"}]
        if path.endswith("/pulls"):
            return [{"number": 3, "state": "open", "merged_at": None, "head": {"sha": "abc"}, "updated_at": "2026-12-01T09:30:00Z",
                     "body": "Left over:\n- do `q/x.py`\n"}]
        if "check-runs" in path:
            return {"check_runs": [{"name": "gate", "conclusion": "failure", "output": {"summary": "boom"}}]}
        if "matching-refs" in path:
            return []
        raise AssertionError(path)

    inp = gather.collect("secondary", {"now": "2026-12-01T10:00:00Z", "sessions": [], "quota": {}, "cloudflare": {}},
                         [], "burst", api=api)
    t = inp["tickets"][0]
    assert [x["number"] for x in inp["tickets"]] == [7]
    assert t["pr"]["ci"] == "red" and "boom" in t["pr"]["failing_output"] and t["claims"][0]["account"] == "secondary"
    assert inp["left_over"][0]["files"] == ["q/x.py"]
