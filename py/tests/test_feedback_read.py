"""T19: read a romanised-Bengali message into asks. The model is replaced by recorded answers; nothing touches the network."""
import json
from pathlib import Path

import pytest

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


























def test_the_real_prompt_and_schema_exist_and_accept_the_recorded_answers():
    assert (runner.PROMPTS / "feedback_read.md").exists()
    schema = runner.schema_path("feedback_read")
    assert schema.name == "feedback_read.schema.json"
    for rec in RECORDED.values():
        runner.validate(rec, schema)




