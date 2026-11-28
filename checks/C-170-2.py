"""C-170-2: an answer citing a number not in the brief, or moving a call without evidence, is rejected and the code-only call stands."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "py/tests/analyse"))
from analyse_support import AnalyseWorker, DAY, door, good_answer, made_up_inputs  # noqa: E402

from stockpilot.jobs.analyse import run  # noqa: E402
from stockpilot.jobs.analyse.answer import code_only, verify  # noqa: E402
from stockpilot.jobs.analyse.brief import build  # noqa: E402
from stockpilot.runtime import run_job  # noqa: E402

D = made_up_inputs()
BRIEF = build("ABC", DAY, facts=D["facts"], history=D["history"], news=D["news"])
CODE = BRIEF["code"]["call"]


def stand(monkeypatch, answer):
    w = AnalyseWorker()
    monkeypatch.setattr("stockpilot.model.client.run_claude", lambda prompt, model, **kw: json.dumps(answer))
    run_job("analyse", lambda ctx: run(ctx), door=door(w), subject="ABC", day=DAY, out=open("/dev/null", "w"))
    assert not w.cache, "a rejected answer must not be stored"
    return w.calls_stored[0]


def test_a_number_not_in_the_brief_is_rejected_and_the_code_call_stands(monkeypatch):
    bad = good_answer(call=CODE)
    bad["reasons"][0]["text_en"] = "Its P/E of 777 is below the sector's 20."
    bad["reasons"][0]["text_bn"] = "এর P/E ৭৭৭, সেক্টরের ২০-এর নিচে।"
    assert not verify(json.dumps(bad), BRIEF).ok
    got = stand(monkeypatch, bad)
    assert got["source"] == "code" and got["call"] == CODE and "777" in got["note"]


def test_a_moved_call_without_evidence_is_rejected(monkeypatch):
    other = "avoid" if CODE != "avoid" else "buy"
    moved = good_answer(call=other)
    moved["reasons"][0]["evidence"] = []
    assert not verify(json.dumps(moved), BRIEF).ok
    got = stand(monkeypatch, moved)
    assert got["source"] == "code" and got["call"] == CODE and got["chance_pct"] == code_only(BRIEF)["chance_pct"]


def test_a_moved_call_with_evidence_stands(monkeypatch):
    other = "avoid" if CODE != "avoid" else "watch"
    ok = good_answer(call=other, moved_because="Plant approval adds capacity.")
    ok["reasons"][0]["evidence"] = ["news:n1"]
    assert verify(json.dumps(ok), BRIEF).ok
