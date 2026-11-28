"""C-130-1: the comparison report needs >=95% form checks and >=80% agreeing verdicts; otherwise Sonnet takes forecasts."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "py/tests/analyse"))
from analyse_support import answer_for  # noqa: E402

from stockpilot.jobs.bench import score  # noqa: E402

ITEMS = score.cases()
BY_PROMPT = {}


def texts(model_calls):
    """Per case: a valid answer with the wanted call, or garbage."""
    out = {}
    for c in ITEMS:
        want = model_calls(c)
        out[c["id"]] = None if want is None else answer_for(c["brief"], call=want) if want != "garbage" else "not json"
    return out


def other(call):
    return "avoid" if call != "avoid" else "buy"


def test_there_are_about_thirty_cases_with_outcomes():
    assert 28 <= len(ITEMS) <= 32
    assert all(isinstance(c["outcome"]["beat"], bool) for c in ITEMS)


def test_haiku_that_passes_both_lines_keeps_forecasts():
    sonnet = score.score_answers(ITEMS, texts(lambda c: c["brief"]["code"]["call"]))
    haiku = score.score_answers(ITEMS, texts(lambda c: c["brief"]["code"]["call"]))
    r = score.comparison(haiku, sonnet)
    assert r["passed"] and r["forecast_model"] == "haiku" and r["form_rate"] == 1.0 and r["agreement"] == 1.0


def test_haiku_failing_the_form_line_moves_forecasts_to_sonnet():
    sonnet = score.score_answers(ITEMS, texts(lambda c: c["brief"]["code"]["call"]))
    bad = {c["id"]: i for i, c in enumerate(ITEMS)}
    haiku = score.score_answers(ITEMS, texts(lambda c: "garbage" if bad[c["id"]] < 3 else c["brief"]["code"]["call"]))
    assert haiku["form_rate"] < score.FORM_MIN
    assert score.comparison(haiku, sonnet)["forecast_model"] == "sonnet"


def test_haiku_disagreeing_on_too_many_verdicts_moves_forecasts_to_sonnet():
    # Its answers move the call without evidence-free: each moved answer carries the brief's evidence, so form passes.
    sonnet = score.score_answers(ITEMS, texts(lambda c: c["brief"]["code"]["call"]))
    haiku = score.score_answers(ITEMS, texts(lambda c: other(c["brief"]["code"]["call"])))
    r = score.comparison(haiku, sonnet)
    assert r["form_rate"] == 1.0 and r["agreement"] < score.AGREE_MIN and r["forecast_model"] == "sonnet"
