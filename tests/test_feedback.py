"""R12: the feedback inbox. Model and GitHub are faked; nothing touches the network."""
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from fake_worker import KEY, FakeWorker
from stockpilot import backup, feedback, store, vmqueue
from stockpilot.sources import kite
from stockpilot.calls import runner

DAY = date(2026, 11, 24)


class FakeGh:
    def __init__(self, closed=()):
        self.calls, self.closed, self.n = [], list(closed), 40

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("issue", "create"):
            self.n += 1
            return f"https://github.com/example/stockpilot/issues/{self.n}\n"
        if args[:2] == ("issue", "list"):
            return json.dumps([{"number": n} for n in self.closed])
        return ""


def model(answers, seen):
    """answers: id -> (category, size, plan). Records the brief it was handed."""
    def analyse(brief, role, runners, **kw):
        seen.append((role, brief))
        return {"runner": "fake", "failures": [], "decisions": {"items": [
            {"id": i["id"], "restatement": f"Wants: {i['text']}", "category": answers[i["id"]][0],
             "size": answers[i["id"]][1], "plan": answers[i["id"]][2]} for i in brief["items"]]}}
    return analyse


def test_feedback_is_stored_as_new_and_shown_as_received(db):
    fid = feedback.add(db, "Please show the P/E on the stock page", "want", "father")
    assert db.execute("select status, author, kind from feedback where id = ?", [fid]).fetchone() == ("new", "father", "want")
    page = feedback.site_payload(db)
    assert [(i["status"], i["text"]) for i in page["items"]] == [("received", "Please show the P/E on the stock page")]


def test_empty_or_bad_feedback_is_refused(db):
    with pytest.raises(ValueError):
        feedback.add(db, "   ", None, "father")
    with pytest.raises(ValueError):
        feedback.add(db, "hi", "praise", "father")


def test_small_copy_change_goes_to_auto_and_a_threshold_change_to_backlog(db):
    a = feedback.add(db, "Say 'Buy' in bigger letters on the call card", "want", "father")
    b = feedback.add(db, "Raise the stop-loss threshold to 12 percent", "want", "owner")
    gh, seen = FakeGh(), []
    out = feedback.triage(db, DAY, model({a: ("wording", "small", "Make the word bigger."),
                                          b: ("rule or money change", "small", "Change the stop to 12%.")}, seen), ["fake"], gh)
    rows = dict(db.execute("select id, status from feedback").fetchall())
    assert rows == {a: "auto", b: "backlog"}
    labels = {c[c.index("--label") + 1] for c in gh.calls if c[:2] == ("issue", "create")}
    assert labels == {"feedback-auto", "feedback-backlog"}
    assert out["status"] == "ok" and out["auto"] == 1 and out["backlog"] == 1
    assert db.execute("select backlog_id from feedback where id = ?", [a]).fetchone()[0] == 41


def test_code_overrides_a_model_that_calls_a_money_or_kite_change_small_wording(db):
    ids = [feedback.add(db, t, "want", "owner") for t in (
        "Let it place the orders for me", "Show the tax on each sale", "Change my budget rule to 2 lakh")]
    seen = []
    feedback.triage(db, DAY, model({i: ("wording", "small", "Tweak the text.") for i in ids}, seen), ["fake"], FakeGh())
    assert {s for (s,) in db.execute("select status from feedback").fetchall()} == {"backlog"}


def test_large_items_wait_in_the_backlog(db):
    a = feedback.add(db, "Add a screen for mutual fund SIPs", "want", "father")
    feedback.triage(db, DAY, model({a: ("new feature", "large", "A new SIP page.")}, []), ["fake"], FakeGh())
    assert db.execute("select status from feedback").fetchone() == ("backlog",)


def test_an_empty_day_skips_the_model(db):
    def boom(*a, **k):
        raise AssertionError("the model must not run")
    out = feedback.triage(db, DAY, boom, ["fake"], FakeGh())
    assert out["status"] == "skipped"


def test_the_model_sees_only_the_feedback_text_no_stock_data(db):
    a = feedback.add(db, "Bigger fonts", "like", "father")
    seen = []
    feedback.triage(db, DAY, model({a: ("wording", "small", "Larger text.")}, seen), ["fake"], FakeGh())
    role, brief = seen[0]
    assert role == "feedback" and set(brief) == {"items"} and set(brief["items"][0]) == {"id", "text", "kind"}


def test_each_label_is_created_before_its_first_issue(db):
    # Found 2026-11-23: on the real repo the labels did not exist, so every issue failed and nothing was filed.
    a = feedback.add(db, "Say 'Buy' in bigger letters on the call card", "want", "father")
    gh = FakeGh()
    feedback.triage(db, DAY, model({a: ("wording", "small", "Make the word bigger.")}, []), ["fake"], gh)
    kinds = [c[:2] for c in gh.calls]
    assert ("label", "create") in kinds
    assert kinds.index(("label", "create")) < kinds.index(("issue", "create"))
    made = [c for c in gh.calls if c[:2] == ("label", "create")][0]
    assert "feedback-auto" in made and "--force" in made


def test_a_failed_model_call_leaves_items_new_and_files_no_issue(db):
    a = feedback.add(db, "Bigger fonts", None, "father")
    gh = FakeGh()

    def fail(*a, **k):
        raise runner.RunnerError("every runner failed")
    out = feedback.triage(db, DAY, fail, ["fake"], gh)
    assert out["status"] == "failed" and gh.calls == []
    assert db.execute("select status from feedback").fetchone() == ("new",)


def test_a_failed_issue_leaves_that_item_new_for_tomorrow(db):
    a = feedback.add(db, "Bigger fonts", None, "father")

    def gh(*args):
        raise RuntimeError("gh is down")
    feedback.triage(db, DAY, model({a: ("wording", "small", "x")}, []), ["fake"], gh)
    assert db.execute("select status from feedback").fetchone() == ("new",)


def test_a_closed_issue_marks_the_item_applied_and_shows_in_what_changed(db):
    a = feedback.add(db, "Bigger fonts", None, "father")
    feedback.triage(db, DAY, model({a: ("wording", "small", "Larger text.")}, []), ["fake"], FakeGh())
    out = feedback.triage(db, date(2026, 11, 25), lambda *a, **k: 1 / 0, ["fake"], FakeGh(closed=[41]))
    assert out["applied"] == 1
    assert db.execute("select status, applied_at is not null from feedback").fetchone() == ("applied", True)
    page = feedback.site_payload(db)
    assert page["last_triage"] == "2026-11-25" and any("Bigger fonts" in c or "Larger text" in c for c in page["changed"])


def test_site_payload_gives_status_plan_last_day_and_changes(db):
    a = feedback.add(db, "Say 'Buy' bigger", "want", "father")
    feedback.triage(db, DAY, model({a: ("wording", "small", "Make the word bigger.")}, []), ["fake"], FakeGh())
    page = feedback.site_payload(db)
    assert page["last_triage"] == "2026-11-24"
    assert page["items"][0]["status"] == "planned" and page["items"][0]["plan"] == "Make the word bigger."
    assert page["changed"]


def test_decide_approve_and_decline(db):
    a = feedback.add(db, "Raise the stop to 12 percent", None, "owner")
    b = feedback.add(db, "Add a screen for mutual fund SIPs", None, "owner")
    feedback.triage(db, DAY, model({a: ("rule or money change", "small", "x"), b: ("new feature", "large", "y")}, []), ["fake"], FakeGh())
    gh = FakeGh()
    assert "approved" in feedback.decide(db, a, "approve", gh).lower()
    assert "declined" in feedback.decide(db, b, "decline", gh).lower()
    assert dict(db.execute("select id, status from feedback").fetchall()) == {a: "auto", b: "declined"}
    verbs = [c[:2] for c in gh.calls]
    assert ("issue", "edit") in verbs and ("issue", "close") in verbs
    with pytest.raises(ValueError):
        feedback.decide(db, a, "maybe", gh)
    with pytest.raises(ValueError):
        feedback.decide(db, 999, "approve", gh)


def test_queue_kinds_store_and_decide(db):
    def item(id_, kind, payload):
        return {"id": id_, "kind": kind, "payload": payload, "by": "father", "at": "2026-11-24T08:00:00Z"}
    w = FakeWorker(queue=[item("001", "feedback", {"text": "Bigger fonts please", "kind": "like"}),
                          item("002", "feedback_decide", {"id": 1, "decision": "decline"}),
                          item("003", "feedback", {"text": ""})])
    try:
        out = vmqueue.poll(db, kite.Worker(w.url, KEY), vmqueue.Context(gh=FakeGh()))
        acks = w.acks
    finally:
        w.close()
    assert [a["status"] for a in acks] == ["done", "done", "failed"]
    assert out == {"done": 2, "failed": 1}
    assert db.execute("select status, kind from feedback").fetchone() == ("declined", "like")


def test_kinds_file_lists_the_feedback_kinds():
    kinds = json.loads((Path(vmqueue.__file__).parents[2] / "schemas" / "queue-kinds.json").read_text())["kinds"]
    assert kinds["feedback"] == ["text", "kind"] and kinds["feedback_decide"] == ["id", "decision"]
    assert "feedback" in backup.STATE_TABLES


def test_triage_schema_checks_the_model_answer():
    schema = json.loads((runner.ROOT / "schemas" / "feedback.schema.json").read_text())
    good = {"items": [{"id": 1, "restatement": "r", "category": "wording", "size": "small", "plan": "p"}]}
    assert runner.schema_errors(good, schema) == []
    assert runner.schema_errors({"items": [{"id": 1}]}, schema)


def test_the_daily_step_triages_then_republishes_and_never_raises(db, monkeypatch):
    from types import SimpleNamespace
    from stockpilot.jobs import daily, ship
    published = []
    monkeypatch.setattr(ship, "publish", lambda m, d, day: published.append(day) or "ok")
    a = feedback.add(db, "Bigger fonts", None, "father")
    m = SimpleNamespace(analyse=model({a: ("wording", "small", "Larger text.")}, []), runners=["fake"], gh=FakeGh())
    out = daily.run_feedback(m, db, datetime(2026, 11, 24, 20, 0))
    assert out["status"] == "ok" and published == [DAY]
    again = daily.run_feedback(m, db, datetime(2026, 11, 24, 20, 5))      # nothing new: no model call, no redeploy
    assert again["status"] == "skipped" and published == [DAY]
    m.analyse = lambda *a, **k: 1 / 0
    feedback.add(db, "More", None, "father")
    assert daily.run_feedback(m, db, datetime(2026, 11, 25, 20, 0))["status"] == "failed"
