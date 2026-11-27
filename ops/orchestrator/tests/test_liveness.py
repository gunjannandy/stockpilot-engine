"""A ticket being built is never given to a second builder, whether or not its session shows in any list."""
from orch_helpers import ago, claim, session, ticket, world

import dispatch
import gather


def starts(plan):
    return [s["ticket"] for s in plan["start"]]


def claimed(minutes, active_minutes_ago, who="s-secondary"):
    return ticket(1, "A", claims=[claim("secondary", minutes, who)], active_at=ago(active_minutes_ago))


def test_recent_github_activity_means_the_ticket_is_not_orphaned():
    assert starts(dispatch.plan(world([claimed(200, 10)]))) == []


def test_a_ticket_quiet_for_90_minutes_is_taken_over():
    assert starts(dispatch.plan(world([claimed(200, 91)]))) == ["A"]


def test_an_archived_claim_session_is_taken_over_at_once():
    gone = session("s-secondary", "A", status="archived")
    assert starts(dispatch.plan(world([claimed(200, 10)], [gone]))) == ["A"]


def test_the_later_of_two_claims_from_one_account_withdraws():
    t = ticket(1, "A", claims=[claim("secondary", 5, "s-first"), claim("secondary", 4, "s-second")], active_at=ago(4))
    plan = dispatch.plan(world([t], session="s-second"))
    assert [w["session"] for w in plan["withdraw"]] == ["s-second"]
    assert starts(plan) == []
    assert dispatch.plan(world([t], session="s-first"))["withdraw"] == []


def test_activity_is_the_newest_of_claim_edit_branch_push_and_pr_update():
    comments = [{"body": "Claimed by secondary: s1", "created_at": "2026-12-01T08:00:00Z",
                 "updated_at": "2026-12-01T09:00:00Z"}]
    issue = {"number": 1, "title": "t", "labels": [], "body": "Key `A`"}
    assert gather.build_ticket(issue, comments)["active_at"] == "2026-12-01T09:00:00Z"
    assert gather.build_ticket(issue, comments, pushed_at="2026-12-01T09:30:00Z")["active_at"] == "2026-12-01T09:30:00Z"
    pr = {"last_push_at": "2026-12-01T09:45:00Z"}
    assert gather.build_ticket(issue, comments, pr, "2026-12-01T09:30:00Z")["active_at"] == "2026-12-01T09:45:00Z"


def test_collect_reads_the_lane_branch_even_before_a_pr_exists():
    issue = {"number": 1, "title": "t", "labels": [{"name": "v3-wave-0"}], "body": "Key `A`"}

    def api(path, *args):
        if path.endswith("/issues"):
            return [issue]
        if path.endswith("/comments"):
            return [{"body": "Claimed by secondary: s1", "created_at": "2026-12-01T08:00:00Z"}]
        if path.endswith("/git/matching-refs/heads/lane/A"):
            return [{"ref": "refs/heads/lane/A", "object": {"sha": "abc"}}]
        if path.endswith("/commits/abc"):
            return {"commit": {"committer": {"date": "2026-12-01T09:55:00Z"}}}
        return []

    state = {"now": "2026-12-01T10:00:00Z", "sessions": [], "quota": {}, "cloudflare": {}, "session": "s9"}
    got = gather.collect("secondary", state, [], "burst", api=api)
    assert got["tickets"][0]["active_at"] == "2026-12-01T09:55:00Z"
    assert got["session"] == "s9"
