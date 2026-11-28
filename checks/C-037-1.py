"""C-037-1: Analyse runs to a call on made-up data, with a progress bar that uses the expected time."""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "py/tests/analyse"))
from analyse_support import AnalyseWorker, DAY, door, good_answer  # noqa: E402

from stockpilot.jobs.analyse import run  # noqa: E402
from stockpilot.runtime import run_job  # noqa: E402


def test_analyse_runs_to_a_call_on_made_up_data(monkeypatch):
    w, out = AnalyseWorker(), io.StringIO()
    monkeypatch.setattr("stockpilot.model.client.run_claude", lambda prompt, model, **kw: json.dumps(good_answer()))
    run_job("analyse", lambda ctx: run(ctx), door=door(w), subject="abc", day=DAY, out=out)
    (stored,) = w.calls_stored
    assert stored["symbol"] == "ABC" and stored["source"] == "model" and stored["call"] == "buy"
    assert stored["summary_en"] and stored["summary_bn"]
    first = json.loads(out.getvalue().splitlines()[0])
    assert "usually about 12 seconds" in first["text"]            # the bar's expected time comes from the Worker's begin answer
