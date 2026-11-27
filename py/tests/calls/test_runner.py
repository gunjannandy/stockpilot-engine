import json
import subprocess

import pytest

from stockpilot.calls import runner

BRIEF = {"as_of": "2026-11-20", "stocks": [{"symbol": "SBIN", "base_rate": 0.55}]}
ITEM = {"symbol": "SBIN", "probability": 0.6, "moved_by": [{"reason": "strong results", "points": 5}], "risks": ["rates"],
        "summary": "Hold SBIN.", "summary_bn": "SBIN ধরে রাখুন।", "level_flag": None, "change_reason": None,
        "would_buy_if": None, "news_used": []}
GOOD = {"market_view": "Calm.", "market_view_bn": "বাজার শান্ত।", "items": [ITEM]}


def fake(stdout, code=0, seen=None):
    def run(cmd, **kw):
        if seen is not None:
            seen.append((cmd, kw))
        return subprocess.CompletedProcess(cmd, code, stdout=stdout, stderr="")
    return run


def test_claude_runner_returns_the_structured_decisions_and_uses_only_the_setup_token():
    seen = []
    out = runner.analyse(BRIEF, "analyst", ["claude"], env={"CLAUDE_CODE_OAUTH_TOKEN": "tok"},
                         run=fake(json.dumps({"is_error": False, "structured_output": GOOD}), seen=seen))
    assert out["decisions"] == GOOD and out["runner"] == "claude"
    cmd, kw = seen[0]
    assert cmd[0] == "claude" and "--json-schema" in cmd
    assert kw["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "tok"
    assert kw["cwd"] != "."                     # an empty folder: the runner sees only the brief


def test_falls_back_to_antigravity_when_claude_cannot_run():
    calls = []

    def run(cmd, **kw):
        calls.append(cmd[0])
        if cmd[0] == "claude":
            return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="usage limit")
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"status": "SUCCESS", "structured_output": GOOD}), stderr="")

    out = runner.analyse(BRIEF, "analyst", ["claude", "agy"], env={"CLAUDE_CODE_OAUTH_TOKEN": "tok"}, run=run)
    assert calls[0] == "claude" and calls[1].endswith("agy")
    assert out["runner"] == "agy" and out["failures"][0]["runner"] == "claude"


def test_claude_is_skipped_without_the_setup_token():
    with pytest.raises(runner.RunnerError) as err:
        runner.analyse(BRIEF, "analyst", ["claude"], env={}, run=fake("{}"))
    assert "CLAUDE_CODE_OAUTH_TOKEN" in str(err.value)


def test_decisions_with_impossible_probabilities_are_rejected():
    bad = {**GOOD, "items": [{**ITEM, "probability": 1.7}]}
    with pytest.raises(runner.RunnerError):
        runner.analyse(BRIEF, "analyst", ["claude"], env={"CLAUDE_CODE_OAUTH_TOKEN": "t"},
                       run=fake(json.dumps({"is_error": False, "structured_output": bad})))


def test_a_missing_cli_is_a_runner_failure_not_a_crash():
    def run(cmd, **kw):
        if cmd[0] == "claude":
            raise FileNotFoundError("claude")
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"status": "SUCCESS", "structured_output": GOOD}), stderr="")

    out = runner.analyse(BRIEF, "analyst", ["claude", "agy"], env={"CLAUDE_CODE_OAUTH_TOKEN": "tok"}, run=run)
    assert out["runner"] == "agy" and "claude" in out["failures"][0]["error"]


def test_the_brief_cap_is_200_000_bytes():
    assert runner.MAX_BRIEF_BYTES == 200_000
    big = {"stocks": ["x" * 150_000, "y" * 60_000]}
    with pytest.raises(runner.RunnerError, match="200000"):
        runner.analyse(big, "analyst", ["claude"], env={"CLAUDE_CODE_OAUTH_TOKEN": "t"}, run=fake("{}"))


def test_the_schema_accepts_a_full_answer_with_bengali_and_a_reason_to_change():
    full = {**GOOD, "items": [{**ITEM, "level_flag": "The target sits just under the 52-week high.",
                               "change_reason": "Results beat; chance up from 52% to 61%.",
                               "would_buy_if": "Buy if it closes above ₹120.", "news_used": ["SBIN-1"]}]}
    assert runner.validate(full) == full


@pytest.mark.parametrize("missing", ["change_reason", "summary_bn", "level_flag", "would_buy_if", "news_used"])
def test_the_schema_rejects_an_item_missing_a_required_field(missing):
    item = {k: v for k, v in ITEM.items() if k != missing}
    with pytest.raises(runner.RunnerError, match=missing):
        runner.validate({**GOOD, "items": [item]})


def test_the_schema_rejects_a_missing_market_view_bn_and_wrong_types():
    with pytest.raises(runner.RunnerError, match="market_view_bn"):
        runner.validate({"market_view": "x", "items": [ITEM]})
    with pytest.raises(runner.RunnerError):
        runner.validate({**GOOD, "items": [{**ITEM, "moved_by": "strong results"}]})
    with pytest.raises(runner.RunnerError):
        runner.validate({**GOOD, "items": [{**ITEM, "probability": "high"}]})


def test_the_model_never_sets_levels_so_the_schema_has_no_entry_stop_or_target():
    props = json.loads(runner.SCHEMA.read_text())["properties"]["items"]["items"]["properties"]
    assert not {"entry", "stop", "target"} & set(props)


def test_the_analyst_prompt_carries_the_plain_words_list_and_never_mentions_the_budget():
    seen = []
    runner.analyse(BRIEF, "analyst", ["claude"], env={"CLAUDE_CODE_OAUTH_TOKEN": "t"},
                   run=fake(json.dumps({"is_error": False, "structured_output": GOOD}), seen=seen))
    prompt = seen[0][1]["input"]
    assert "{{plain-words}}" not in prompt and "stop-loss" in prompt and "BRIEF:" in prompt
    for role in ("analyst", "skeptic", "plain-words"):
        assert "budget" not in (runner.PROMPTS / f"{role}.md").read_text().lower()


def test_jargon_in_the_models_words_is_found_by_the_banned_list():
    assert "stop-loss" in runner.jargon_in("Place a stop-loss at 929 and wait for a catalyst.")
    assert runner.jargon_in("If it falls to ₹929, sell.") == []


def test_claude_gets_the_prompt_on_stdin_because_one_argument_is_capped_at_128_kb():
    big = {**BRIEF, "pad": "x" * 150_000}          # the real brief was 169 KB: argv failed with "Argument list too long"
    seen = []
    runner.analyse(big, "analyst", ["claude"], env={"CLAUDE_CODE_OAUTH_TOKEN": "t"},
                   run=fake(json.dumps({"is_error": False, "structured_output": GOOD}), seen=seen))
    cmd, kw = seen[0]
    assert all(len(a) < 100_000 for a in cmd) and "-p" in cmd and len(kw["input"]) > 150_000
