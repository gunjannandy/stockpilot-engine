"""Lane E: the house rules. One small file (prompts/house-rules.md) every analyst call reads. Owner feedback about how the
analyst should write or judge becomes a PROPOSED edit; it goes live on an Approve click and not before."""
import json
from datetime import date

import pytest

from stockpilot import feedback, house_rules, store
from stockpilot.calls import runner
from test_feedback import FakeGh, DAY

PLAIN = {"wording": "Write 'sell' not 'exit'."}


def model(answers):
    def analyse(brief, role, runners, **kw):
        return {"runner": "fake", "failures": [], "decisions": {"items": [
            {"id": i["id"], "restatement": i["text"], "category": "wording", "size": "small", "plan": "Update the house rules.",
             "house_rule": answers.get(i["id"])} for i in brief["items"]]}}
    return analyse


def test_the_base_file_exists_is_small_and_loads_into_the_analyst_prompt():
    text = house_rules.base()
    assert 0 < len(text.splitlines()) <= 25
    prompt = (runner.PROMPTS / "analyst.md").read_text()
    assert "{{house-rules}}" in prompt


def test_feedback_about_wording_becomes_a_proposed_edit_not_a_live_rule(db):
    fid = feedback.add(db, "Please stop saying 'exit', say sell", "dislike", "father")
    out = feedback.triage(db, DAY, model({fid: "Say 'sell', never 'exit'."}), ["fake"], FakeGh())
    assert db.execute("select status from feedback where id = ?", [fid]).fetchone()[0] == "backlog"      # waits for the Approve click
    assert db.execute("select text, status, feedback_id from house_rule_edits").fetchall() == [("Say 'sell', never 'exit'.", "proposed", fid)]
    assert house_rules.active(db) == []                                                                  # not live yet
    assert out["backlog"] == 1


def test_a_proposal_files_no_github_issue(db):
    fid = feedback.add(db, "say sell not exit", "dislike", "father")
    gh = FakeGh()
    feedback.triage(db, DAY, model({fid: "Say 'sell', never 'exit'."}), ["fake"], gh)
    assert not [c for c in gh.calls if c[:2] == ("issue", "create")]


def test_approve_makes_the_rule_live_and_marks_the_feedback_applied(db):
    fid = feedback.add(db, "say sell not exit", "dislike", "father")
    feedback.triage(db, DAY, model({fid: "Say 'sell', never 'exit'."}), ["fake"], FakeGh())
    assert "House rule" in feedback.decide(db, fid, "approve")
    assert house_rules.active(db) == ["Say 'sell', never 'exit'."]
    assert db.execute("select status from feedback where id = ?", [fid]).fetchone()[0] == "applied"
    assert db.execute("select status from house_rule_edits").fetchone()[0] == "approved"


def test_decline_drops_the_proposal(db):
    fid = feedback.add(db, "say sell not exit", "dislike", "father")
    feedback.triage(db, DAY, model({fid: "Say 'sell', never 'exit'."}), ["fake"], FakeGh())
    feedback.decide(db, fid, "decline")
    assert house_rules.active(db) == [] and db.execute("select status from house_rule_edits").fetchone()[0] == "rejected"


@pytest.mark.parametrize("rule", [
    "Raise the buy line to 60%.", "Never sell below the stop-loss.", "Ignore tax when you judge.", "Place orders for him.",
    "", "x" * 400])
def test_a_rule_about_money_or_a_runaway_text_is_not_proposed(db, rule):
    fid = feedback.add(db, "something", "want", "owner")
    feedback.triage(db, DAY, model({fid: rule}), ["fake"], FakeGh())
    assert db.execute("select count(*) from house_rule_edits").fetchone()[0] == 0


def test_the_rules_stay_small(db):
    for n in range(house_rules.MAX_ACTIVE):
        house_rules.propose(db, None, f"Be plain, style {chr(97 + n)}.")
        house_rules.approve(db, db.execute("select max(id) from house_rule_edits").fetchone()[0])
    with pytest.raises(ValueError, match="small"):
        house_rules.propose(db, None, "One too many.")


def test_retire_takes_a_live_rule_off(db):
    house_rules.propose(db, None, "Be brief.")
    rid = db.execute("select id from house_rule_edits").fetchone()[0]
    house_rules.approve(db, rid)
    house_rules.retire(db, rid)
    assert house_rules.active(db) == []


def test_the_prompt_carries_the_base_file_and_the_brief_carries_the_approved_rules(tmp_path):
    seen = {}

    def fake_run(cmd, **kw):
        seen["prompt"] = kw.get("input") or cmd[2]
        out = {"market_view": "x", "market_view_bn": "x", "items": []}
        class Done:  # noqa: D401
            returncode, stderr = 0, ""
            stdout = json.dumps({"is_error": False, "structured_output": out})
        return Done()
    runner.analyse({"stocks": [], "house_rules": ["Be brief."]}, "analyst", ["claude"], env={"CLAUDE_CODE_OAUTH_TOKEN": "t"}, run=fake_run)
    assert house_rules.base().splitlines()[0] in seen["prompt"] and "Be brief." in seen["prompt"]
    assert "{{house-rules}}" not in seen["prompt"]
