"""C-077-1: fund Analyse runs to a fund call (buy or watch), English and Bengali from one call, checked before it is stored."""
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "py/tests/analyse"))
from analyse_support import DAY, FundWorker, answer_for, door  # noqa: E402

from stockpilot.jobs.analyse.answer import verify  # noqa: E402
from stockpilot.jobs.fundcall import run  # noqa: E402
from stockpilot.jobs.fundcall.brief import build, check_public  # noqa: E402
from stockpilot.runtime import run_job  # noqa: E402


def go(monkeypatch, answer_text):
    w = FundWorker()
    monkeypatch.setattr("stockpilot.model.client.run_claude", lambda prompt, model, **kw: answer_text)
    run_job("fundcall", lambda ctx: run(ctx), door=door(w), subject="f1", day=DAY, out=io.StringIO())
    return w.calls_stored[0], w


def brief():
    w = FundWorker()
    return build("f1", DAY, fund=w.fund, call_row=w.call)


def test_fund_analyse_runs_to_a_fund_call(monkeypatch):
    b = brief()
    assert b["code"] == {"call": "buy", "chance_pct": 64} and b["calls"] == ["buy", "watch"]
    stored, _ = go(monkeypatch, answer_for(b))
    assert stored["fund"] == "f1" and stored["source"] == "model" and stored["call"] == "buy"
    assert stored["summary_en"] and stored["summary_bn"]


def test_a_fund_call_outside_buy_or_watch_is_rejected_and_the_code_call_stands(monkeypatch):
    b = brief()
    assert not verify(answer_for(b, call="avoid"), b).ok
    stored, w = go(monkeypatch, answer_for(b, call="avoid"))
    assert stored["source"] == "code" and stored["call"] == "buy" and not w.cache


def test_the_fund_brief_has_no_holding_sip_or_tax_field():
    check_public(brief())
    assert not [k for k in json.dumps(brief()).lower().split('"') if k in ("holding", "sip", "tax", "lots")]
