"""C-039-1: a model answer without Bengali is rejected."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "py/tests/analyse"))
from analyse_support import DAY, good_answer, made_up_inputs  # noqa: E402

from stockpilot.jobs.analyse.answer import verify  # noqa: E402
from stockpilot.jobs.analyse.brief import build  # noqa: E402

D = made_up_inputs()
BRIEF = build("ABC", DAY, facts=D["facts"], history=D["history"], news=D["news"])


def test_an_answer_without_bengali_is_rejected():
    import json
    assert verify(json.dumps(good_answer()), BRIEF).ok
    assert not verify(json.dumps(good_answer(summary_bn="Cheap against its sector.")), BRIEF).ok
    bad = good_answer()
    bad["reasons"][0]["text_bn"] = ""
    v = verify(json.dumps(bad), BRIEF)
    assert not v.ok and any("no Bengali" in r for r in v.reasons)
