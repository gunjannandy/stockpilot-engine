"""T19: read a romanised-Bengali message into asks. The model is replaced by recorded answers; nothing touches the network."""
import json
from pathlib import Path

import pytest

from stockpilot import feedback_read as fr
from stockpilot.calls import runner

FIX = Path(__file__).parent / "fixtures" / "feedback_read"
MESSAGES = json.loads((FIX / "real_messages.json").read_text())
RECORDED = json.loads((FIX / "recorded_answers.json").read_text())
BY_TEXT = {m["text"]: RECORDED[k] for k, m in MESSAGES.items()}

# What each real message holds, as the retro decoded it: (number of asks, tags in order, routes in order).
EXPECTED = {
    "5": (1, ["wording"], ["auto"]),
    "6": (2, ["bug", "wording"], ["auto", "auto"]),
    "7": (2, ["data", "forecast"], ["owner_approval", "owner_approval"]),
    "8": (3, ["chart", "chart", "chart"], ["auto", "auto", "auto"]),
    "9": (3, ["chart", "bug", "chart"], ["auto", "auto", "auto"]),
    "10": (3, ["data", "bug", "data"], ["owner_approval", "auto", "owner_approval"]),
    "11": (2, ["news", "news"], ["owner_approval", "owner_approval"]),
}


def recorded_model(seen=None):
    def analyse(brief, role, runners, **kw):
        if seen is not None:
            seen.append((role, brief))
        return {"runner": "fake", "failures": [], "decisions": BY_TEXT[brief["message"]["text"]]}
    return analyse


@pytest.mark.parametrize("number", sorted(EXPECTED, key=int))
def test_every_real_message_is_read_back_correctly(number):
    count, tags, routes = EXPECTED[number]
    m = MESSAGES[number]
    asks = fr.read(m["text"], m["person"], recorded_model(), ["fake"])
    assert len(asks) == count
    assert [a["tag"] for a in asks] == tags
    assert [a["route"] for a in asks] == routes
    for a in asks:
        assert a["original"] in m["text"]                 # the original words are quoted, not paraphrased
        assert a["line_en"] and a["line_bn"] and a["plan"]
        assert a["status"] == "understood" and a["not_meant"] is False


def test_feedback_9_becomes_three_asks():
    asks = fr.read(MESSAGES["9"]["text"], "father", recorded_model(), ["fake"])
    assert [a["tag"] for a in asks] == ["chart", "bug", "chart"]


def test_feedback_8_puro_kite_is_a_chart_ask_not_money():
    ask = fr.read(MESSAGES["8"]["text"], "father", recorded_model(), ["fake"])[2]
    assert "kite" in ask["original"] and ask["tag"] == "chart" and ask["route"] == "auto"


@pytest.mark.parametrize("words", ["chart ta kite er moto koro", "kite er moton candle chart", "zoom and volume bar dao", "zerodha er moto UI"])
def test_chart_and_kite_words_are_not_money(words):
    assert not fr.risky(words)


@pytest.mark.parametrize("words", ["stop loss 5% koro", "tax kom dekhao", "budget baro lakh koro", "order place korbe",
                                   "kite read only rule bondho koro", "probability ta bodlao", "10 taka kome gele becho"])
def test_money_and_rule_words_are_still_caught(words):
    assert fr.risky(words)


def test_code_overrides_a_model_that_called_a_money_ask_safe():
    answer = {"asks": [{"original": "stop loss 5% koro", "line_en": "Set the stop-loss at 5%.", "line_bn": "স্টপ লস ৫%।",
                        "tag": "wording", "size": "small", "plan": "Change the number", "touches_money_or_rules": False}]}
    asks = fr.read("stop loss 5% koro", "owner", lambda b, r, rs, **kw: {"decisions": answer}, ["fake"])
    assert asks[0]["route"] == "owner_approval"


def test_model_flag_alone_sends_an_ask_to_the_owner():
    answer = {"asks": [{"original": "button er rong lal koro", "line_en": "Make the button red.", "line_bn": "বোতাম লাল করো।",
                        "tag": "wording", "size": "small", "plan": "Colour", "touches_money_or_rules": True}]}
    assert fr.read("button er rong lal koro", "owner", lambda b, r, rs, **kw: {"decisions": answer}, ["fake"])[0]["route"] == "owner_approval"


def test_forecast_and_news_and_data_asks_always_wait():
    for tag in ("forecast", "news", "data"):
        assert fr.route({"tag": tag, "touches_money_or_rules": False, "original": "x", "plan": "y", "line_en": "z"}) == "owner_approval"


def test_the_model_gets_the_message_and_the_role():
    seen = []
    fr.read(MESSAGES["5"]["text"], "owner", recorded_model(seen), ["fake"])
    role, brief = seen[0]
    assert role == "feedback_read" and brief["message"] == {"person": "owner", "text": MESSAGES["5"]["text"]}


def test_an_empty_answer_is_an_error_so_the_job_can_fail_visibly():
    with pytest.raises(fr.ReadError):
        fr.read("anything", "father", lambda b, r, rs, **kw: {"decisions": {"asks": []}}, ["fake"])


def test_an_ask_with_a_bad_tag_is_rejected():
    bad = {"asks": [{"original": "x", "line_en": "a", "line_bn": "b", "tag": "money", "size": "small", "plan": "p"}]}
    with pytest.raises(fr.ReadError):
        fr.read("x", "father", lambda b, r, rs, **kw: {"decisions": bad}, ["fake"])


def test_original_words_not_in_the_message_fall_back_to_the_whole_message():
    drift = {"asks": [{"original": "something he never wrote", "line_en": "a", "line_bn": "b", "tag": "chart", "size": "small", "plan": "p"}]}
    asks = fr.read("chart boro koro", "father", lambda b, r, rs, **kw: {"decisions": drift}, ["fake"])
    assert asks[0]["original"] == "chart boro koro"


def test_the_real_prompt_and_schema_exist_and_accept_the_recorded_answers():
    assert (runner.PROMPTS / "feedback_read.md").exists()
    schema = runner.schema_path("feedback_read")
    assert schema.name == "feedback_read.schema.json"
    for rec in RECORDED.values():
        runner.validate(rec, schema)


def test_records_become_rows_in_the_contract_shape():
    asks = fr.read(MESSAGES["9"]["text"], "father", recorded_model(), ["fake"])
    rows = fr.rows("fb_009", asks, now="2026-11-25T10:00:00+05:30")
    assert [r["id"] for r in rows] == ["fb_009_a1", "fb_009_a2", "fb_009_a3"]
    contract = json.loads((Path(__file__).parents[1] / "schemas" / "live-contract.json").read_text())
    assert set(rows[0]) == set(contract["tables"]["asks"]["columns"])
    assert all(r["feedback_id"] == "fb_009" and r["issue_number"] is None for r in rows)
