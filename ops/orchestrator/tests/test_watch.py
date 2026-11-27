"""The VM watcher: GitHub state in, orchestrator wake-up events out. Made-up data only."""
from orch_helpers import NOW, ago
import watch

CFG = {"accounts": [{"name": "primary", "slots": 2}, {"name": "secondary", "slots": 2}], "quiet_minutes": 60}


def t(number, key, **kw):
    d = {"number": number, "key": key, "labels": ["ready-for-agent"], "blocked_by": [], "open_blockers": [],
         "ui": False, "claim": None, "pr": None, "pushed_at": None}
    d.update(kw)
    return d


def events(tickets, me="primary", state=None):
    ev, _ = watch.decide(tickets, state or {}, NOW, CFG, me)
    return ev


def test_a_ready_ticket_is_started_on_primary_first():
    assert events([t(1, "A")]) == [{"kind": "start", "account": "primary", "number": 1, "key": "A"}]
    assert events([t(1, "A")], me="secondary") == []


def building(account, minutes_ago=5, session="s1"):
    return {"account": account, "session": session, "at": ago(minutes_ago)}


def test_secondary_takes_what_primary_has_no_slot_for_but_never_a_ui_ticket():
    full = [t(1, "A", claim=building("primary")), t(2, "B", claim=building("primary"))]
    assert events(full + [t(3, "C")], me="secondary") == [
        {"kind": "start", "account": "secondary", "number": 3, "key": "C"}]
    assert events(full + [t(3, "C", ui=True)], me="secondary") == []


def test_blocked_or_waiting_tickets_never_start():
    assert events([t(1, "A", open_blockers=[9]), t(2, "B", labels=["needs-planner"])]) == []


def test_an_account_at_its_limit_starts_nothing_and_resumes_once_the_reset_passes():
    limited = {"limited_until": {"primary": ago(-30)}}
    assert events([t(1, "A")], state=limited, me="secondary")[0]["account"] == "secondary"
    assert events([t(1, "A")], state=limited) == []
    passed = {"limited_until": {"primary": ago(1)}}
    ev, st = watch.decide([], passed, NOW, CFG, "primary")
    assert ev == [{"kind": "resume", "account": "primary"}]
    assert "primary" not in st["limited_until"]


def pr(state="open", ci="pending", sha="abc", updated=5, number=7):
    return {"number": number, "state": state, "ci": ci, "head_sha": sha, "updated_at": ago(updated)}


def test_a_merged_ticket_is_reported_done_once_with_its_builder_and_left_overs():
    x = t(1, "A", claim=building("primary", session="s9"), pr=dict(pr("merged"), left_over=["`x/y.ts` later"]))
    ev, st = watch.decide([x], {}, NOW, CFG, "primary")
    assert ev == [{"kind": "done", "account": "primary", "number": 1, "key": "A", "session": "s9", "pr": 7,
                   "left_over": ["`x/y.ts` later"]}]
    assert watch.decide([x], st, NOW, CFG, "primary")[0] == []


def test_another_accounts_builders_are_not_mine_to_report():
    x = t(1, "A", claim=building("secondary"), pr=pr("merged"))
    assert events([x]) == []


def test_a_builder_quiet_on_github_for_an_hour_is_checked_then_rechecked_an_hour_later():
    x = t(1, "A", claim=building("primary", minutes_ago=200, session="s9"), pushed_at=ago(61))
    ev, st = watch.decide([x], {}, NOW, CFG, "primary")
    assert ev == [{"kind": "check", "why": "quiet", "account": "primary", "number": 1, "key": "A",
                   "session": "s9", "minutes": 61}]
    assert watch.decide([x], st, NOW, CFG, "primary")[0] == []
    assert events([t(1, "A", claim=building("primary", minutes_ago=200), pushed_at=ago(20))]) == []


def test_red_ci_is_reported_once_per_commit_after_the_builder_had_20_minutes():
    x = t(1, "A", claim=building("primary", minutes_ago=90, session="s9"), pr=pr(ci="red", updated=25), pushed_at=ago(25))
    ev, st = watch.decide([x], {}, NOW, CFG, "primary")
    assert [e["why"] for e in ev] == ["red"]
    assert watch.decide([x], st, NOW, CFG, "primary")[0] == []
    assert events([t(1, "A", claim=building("primary"), pr=pr(ci="red", updated=5), pushed_at=ago(5))]) == []


def test_a_prototype_waiting_is_reported_once():
    x = t(1, "A", ui=True, labels=["prototype-waiting"], claim=building("primary", session="s9"), pushed_at=ago(90))
    ev, st = watch.decide([x], {}, NOW, CFG, "primary")
    assert ev == [{"kind": "prototype", "account": "primary", "number": 1, "key": "A", "session": "s9"}]
    assert watch.decide([x], st, NOW, CFG, "primary")[0] == []


def test_the_orchestrators_context_is_read_from_its_transcript(tmp_path):
    f = tmp_path / "s.jsonl"
    f.write_text('{"type":"user","message":{"content":"hi"}}\n'
                 '{"type":"assistant","message":{"usage":{"input_tokens":5,"cache_read_input_tokens":90000,'
                 '"cache_creation_input_tokens":1000}}}\n{"type":"assistant","message":{"usage":{"input_tokens":3,'
                 '"cache_read_input_tokens":120000,"cache_creation_input_tokens":2000}}}\n')
    assert watch.context_tokens(f) == 122003


def test_an_issue_becomes_a_ticket_with_its_claim_blockers_and_left_over_key():
    issue = {"number": 5, "title": "v3 X", "labels": [{"name": "ready-for-agent"}, {"name": "v3-ui"}],
             "body": "Key `X`.\n\nBlocked by: #3, #4\n"}
    comments = [{"body": "Claimed by primary: s1", "created_at": ago(30)},
                {"body": "Withdrawn by primary: s1", "created_at": ago(20)},
                {"body": "Claimed by secondary: s2", "created_at": ago(10)}]
    x = watch.to_ticket(issue, comments, open_numbers={4, 5})
    assert (x["key"], x["ui"], x["blocked_by"], x["open_blockers"]) == ("X", True, [3, 4], [4])
    assert x["claim"] == {"account": "secondary", "session": "s2", "at": ago(10)}
    left = watch.to_ticket({"number": 198, "title": "y", "labels": [], "body": "Left over from SIGNIN."}, [], set())
    assert left["key"] == "LO198" and left["claim"] is None
