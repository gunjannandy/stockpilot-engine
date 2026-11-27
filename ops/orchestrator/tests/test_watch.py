"""The VM watcher: GitHub state in, orchestrator wake-up events out. Made-up data only."""
from orch_helpers import NOW, ago
import watch

CFG = {"accounts": [{"name": "secondary", "slots": 2}, {"name": "primary", "slots": 2, "reserve": True}],
       "quiet_minutes": 60}


def t(number, key, **kw):
    d = {"number": number, "key": key, "labels": ["ready-for-agent"], "blocked_by": [], "open_blockers": [],
         "ui": False, "claim": None, "pr": None, "pushed_at": None}
    d.update(kw)
    return d


def events(tickets, me="primary", state=None):
    ev, _ = watch.decide(tickets, state or {}, NOW, CFG, me)
    return ev


def test_a_ready_ticket_is_started_on_secondary_first():
    assert events([t(1, "A")], me="secondary") == [{"kind": "start", "account": "secondary", "number": 1, "key": "A"}]
    assert events([t(1, "A")]) == []


def building(account, minutes_ago=5, session="s1"):
    return {"account": account, "session": session, "at": ago(minutes_ago)}


def test_the_reserve_account_waits_while_secondary_is_merely_full():
    full = [t(1, "A", claim=building("secondary")), t(2, "B", claim=building("secondary"))]
    assert events(full + [t(3, "C")]) == []
    assert events(full + [t(3, "C", ui=True)], me="secondary") == []


def test_blocked_or_waiting_tickets_never_start():
    assert events([t(1, "A", open_blockers=[9]), t(2, "B", labels=["needs-planner"])]) == []


def test_an_account_at_its_limit_starts_nothing_and_resumes_once_the_reset_passes():
    limited = {"limited_until": {"secondary": ago(-30)}}
    assert events([t(1, "A")], state=limited)[0]["account"] == "primary"
    assert events([t(1, "A")], state=limited, me="secondary") == []
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
    assert events([x], me="secondary")[0]["kind"] == "done"


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


def test_a_usage_limit_is_read_from_the_accounts_own_transcripts(tmp_path):
    f = tmp_path / "s.jsonl"
    f.write_text('{"type":"assistant","timestamp":"2026-12-01T08:00:00Z","error":"rate_limit","isApiErrorMessage":true,'
                 '"message":{"content":[{"type":"text","text":"You\'ve hit your 5-hour limit \u00b7 resets 5:20pm '
                 '(Asia/Kolkata)"}]}}\n')
    assert watch.limit_from_transcripts([f], NOW) == "2026-12-01T17:20:00+05:30"
    assert watch.limit_from_transcripts([f], "2026-12-01T12:00:00+00:00") is None


def test_every_ticket_gets_one_status_label_agents_can_list():
    tickets = [t(1, "A"), t(2, "B", open_blockers=[1]), t(3, "C", claim=building("secondary")),
               t(4, "D", claim=building("secondary"), pr=pr()), t(5, "E", labels=["prototype-waiting"],
               claim=building("secondary")), t(6, "F", labels=["needs-planner"])]
    assert [watch.status(x) for x in tickets] == ["status:ready", "status:blocked", "status:building",
                                                  "status:pr", "status:prototype", "status:stuck"]


def test_a_red_main_wakes_the_active_account_once_per_commit():
    ev, st = watch.decide([], {}, NOW, CFG, "secondary", main={"sha": "m1", "ci": "red"})
    assert ev == [{"kind": "main-red", "account": "secondary", "sha": "m1"}]
    assert watch.decide([], st, NOW, CFG, "secondary", main={"sha": "m1", "ci": "red"})[0] == []
    assert watch.decide([], {}, NOW, CFG, "primary", main={"sha": "m1", "ci": "red"})[0] == []


def test_the_board_puts_what_needs_the_owner_first_then_building_then_counts():
    tickets = [t(1, "A", claim=building("secondary", session="s1"), pr=pr(ci="green", number=10)),
               t(2, "B", labels=["prototype-waiting"], claim=building("secondary", session="s2")),
               t(3, "C", labels=["needs-owner"], claim=building("secondary", session="s3"),
                 ask="Reply \"label 15\" to approve."),
               t(4, "D"), t(5, "E", open_blockers=[4])]
    md = watch.board(tickets, {"limited_until": {"secondary": ago(-60)}}, NOW)
    needs, building_, rest = md.index("## Needs you"), md.index("## Building"), md.index("## Queue")
    assert needs < building_ < rest
    assert "#3" in md[needs:building_] and "label 15" in md[needs:building_] and "#2" in md[needs:building_]
    assert "#1" in md[building_:rest] and "engine#10" in md[building_:rest]
    assert "Ready: 1" in md and "Blocked: 1" in md and "secondary (works first): at its limit until 16:30 IST" in md


def test_an_owner_reply_on_a_ticket_that_needs_him_wakes_its_orchestrator_once():
    x = t(3, "C", labels=["needs-owner"], claim=building("secondary", session="s3"), owner_reply=("c77", "label 15"))
    ev, st = watch.decide([x], {}, NOW, CFG, "secondary")
    assert {"kind": "owner-reply", "account": "secondary", "number": 3, "key": "C", "text": "label 15"} in ev
    assert watch.decide([x], st, NOW, CFG, "secondary")[0] == []


def test_prototypes_waiting_for_the_owner_do_not_fill_the_slots():
    waiting = [t(i, "P%d" % i, ui=True, labels=["v3-ui", "prototype-waiting"], claim=building("primary", session="s%d" % i))
               for i in (1, 2, 3)]
    ev = events(waiting + [t(4, "D", ui=True)], state={"limited_until": {"secondary": "2099-01-01T00:00:00Z"}})
    assert [e["number"] for e in ev if e["kind"] == "start"] == [4]


def test_a_quiet_ui_builder_is_never_checked():
    x = t(1, "A", ui=True, claim=building("primary", minutes_ago=300, session="s9"), pushed_at=ago(240))
    assert events([x]) == []
