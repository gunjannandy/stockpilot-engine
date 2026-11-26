"""ASKS (spec #24 stories 87 and 88): every approved or automatic ask becomes a GitHub ticket quoting the father's own words, and when
the ticket closes the ask moves to Done. GitHub is a fake `gh(args) -> stdout`; D1 is the real migrations on SQLite."""
import json

from stockpilot import ask_tickets
from test_wire import d1

AT = "2026-11-26T10:00:00+05:30"
ORIGINAL = "chart ta Kite er moto kore dao"


class FakeGh:
    """Records every call; `issues` is what `GET issues` returns, and a create adds one."""

    def __init__(self, issues=None):
        self.calls, self.issues, self.next = [], issues or [], 200

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["api", "-X"] and args[2] == "POST":
            body = dict(a.split("=", 1) for a in args if "=" in a and not a.startswith("repos/"))
            self.next += 1
            issue = {"number": self.next, "body": body.get("body", ""), "state": "open"}
            self.issues.append(issue)
            return json.dumps(issue)
        return json.dumps(self.issues)

    def creates(self):
        return [c for c in self.calls if "POST" in c]


def seed(query, aid="f1_a1", status="understood", route="auto", issue=None, not_meant=0, person="father", tag="chart"):
    query("insert or ignore into feedback (id, person, text, status, created_at) values ('f1', ?, ?, 'understood', ?)", [person, ORIGINAL, AT])
    query("insert into asks (id, feedback_id, original, line_en, line_bn, tag, size, plan, route, status, not_meant, issue_number, updated_at) "
          "values (?, 'f1', ?, 'Make the chart like Kite.', 'চার্ট Kite-এর মতো করুন।', ?, 'small', 'Copy the zoom and drag.', ?, ?, ?, ?, ?)",
          [aid, ORIGINAL, tag, route, status, not_meant, issue, AT])


def ask(query, aid="f1_a1"):
    return query("select * from asks where id = ?", [aid])[0]


def test_an_automatic_ask_becomes_a_ticket_that_quotes_the_original_words():
    _, q = d1(); seed(q); gh = FakeGh()
    out = ask_tickets.run(q, gh, AT)
    assert out == {"filed": 1, "done": 0}
    row = ask(q)
    assert row["status"] == "being_built" and row["issue_number"] == 201
    body = gh.issues[0]["body"]
    assert f"> {ORIGINAL}" in body and "Make the chart like Kite." in body and "Said by father" in body and "<!-- ask:f1_a1 -->" in body
    create = " ".join(gh.creates()[0])
    assert "ready-for-agent" in create and "from-feedback" in create and "auto" in create


def test_an_ask_the_owner_approved_is_filed_with_the_approved_label():
    _, q = d1(); seed(q, status="being_built", route="owner_approval"); gh = FakeGh()
    ask_tickets.run(q, gh, AT)
    assert ask(q)["issue_number"] == 201 and ask(q)["status"] == "being_built"
    assert "owner-approved" in " ".join(gh.creates()[0]) and "auto" not in " ".join(gh.creates()[0]).replace("owner-approved", "")


def test_asks_that_wait_are_declined_or_not_meant_get_no_ticket_and_cost_no_github_call():
    _, q = d1()
    seed(q, "f1_a1", status="waiting_for_approval", route="owner_approval")
    seed(q, "f1_a2", status="declined", route="owner_approval")
    seed(q, "f1_a3", status="understood", route="auto", not_meant=1)
    gh = FakeGh()
    assert ask_tickets.run(q, gh, AT) == {"filed": 0, "done": 0} and gh.calls == []


def test_a_crash_between_filing_and_saving_does_not_file_twice():
    _, q = d1(); seed(q)
    gh = FakeGh(issues=[{"number": 77, "body": "x\n<!-- ask:f1_a1 -->", "state": "open"}])
    ask_tickets.run(q, gh, AT)
    assert gh.creates() == [] and ask(q)["issue_number"] == 77 and ask(q)["status"] == "being_built"


def test_a_closed_ticket_moves_the_ask_to_done_and_the_author_gets_a_yellow_mark_once():
    _, q = d1(); seed(q, status="being_built", issue=55)
    gh = FakeGh(issues=[{"number": 55, "body": "", "state": "closed", "state_reason": "completed"}])
    assert ask_tickets.run(q, gh, AT) == {"filed": 0, "done": 1}
    assert ask(q)["status"] == "done"
    marks = q("select person, symbol, kind, new_value from changes")
    assert marks == [{"person": "father", "symbol": "feedback", "kind": "ask_status", "new_value": "done"}]
    ask_tickets.run(q, gh, AT)
    assert len(q("select * from changes")) == 1


def test_a_ticket_closed_as_not_planned_declines_the_ask_and_an_open_one_leaves_it_building():
    _, q = d1()
    seed(q, "f1_a1", status="being_built", issue=55)
    seed(q, "f1_a2", status="being_built", issue=56)
    gh = FakeGh(issues=[{"number": 55, "body": "", "state": "closed", "state_reason": "not_planned"},
                        {"number": 56, "body": "", "state": "open"}])
    ask_tickets.run(q, gh, AT)
    assert ask(q, "f1_a1")["status"] == "declined" and ask(q, "f1_a2")["status"] == "being_built"


def test_one_github_read_serves_every_open_ask():
    _, q = d1()
    for n in range(1, 5):
        seed(q, f"f1_a{n}", status="being_built", issue=50 + n)
    gh = FakeGh(issues=[{"number": 51, "body": "", "state": "closed", "state_reason": "completed"}])
    ask_tickets.run(q, gh, AT)
    assert len(gh.calls) == 1
