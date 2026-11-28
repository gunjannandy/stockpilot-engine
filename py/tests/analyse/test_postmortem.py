import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analyse_support import DAY, door  # noqa: E402
from fake_runtime_worker import FakeRuntimeWorker  # noqa: E402

from stockpilot.jobs.analyse.brief import PrivateField  # noqa: E402
from stockpilot.jobs.postmortem import build, code_row, run, verify  # noqa: E402
from stockpilot.runtime import run_job  # noqa: E402

DUE = {"key": "ABC|2026-08-01", "symbol": "ABC", "day": "2026-08-01", "call": "buy", "chance_pct": 62,
       "summary_en": "Cheap.", "reasons": [{"text_en": "P/E 12 is low."}], "risks": [{"text_en": "Metal prices can fall."}],
       "stock_pct": 5.0, "nifty_pct": 10.0, "excess_pct": -5.0, "end_day": "2026-10-31",
       "news_after": [{"title": "Probe opened", "direction": "bad", "why_en": "Raises costs"}]}


class W(FakeRuntimeWorker):
    def __init__(self, due=None, **kw):
        super().__init__(**kw)
        self.due, self.rows = {"calls": [DUE]} if due is None else due, []

    def transport(self, method, url, headers, body):
        route = "/" + url.split("/", 3)[3]
        if route == "/api/postmortem/due":
            return 200, self.due
        if route == "/api/postmortem/row":
            self.rows.append(json.loads(body))
            return 200, {"written": 1}
        return super().transport(method, url, headers, body)


def good(**over):
    return json.dumps({"cause": "news_after", "why_en": "A probe opened and the stock ended 5 points behind.",
                       "why_bn": "একটি তদন্ত শুরু হয় এবং শেয়ার 5 পয়েন্ট পিছিয়ে শেষ করে।", "evidence": ["news:0"], **over},
                      ensure_ascii=False)


def go(w, text, monkeypatch):
    monkeypatch.setattr("stockpilot.model.client.run_claude", lambda prompt, model, **kw: text)
    run_job("postmortem", lambda ctx: run(ctx), door=door(w), day=DAY, out=io.StringIO())


def test_a_missed_call_gets_one_row_from_the_model(monkeypatch):
    w = W()
    go(w, good(), monkeypatch)
    (row,) = w.rows
    assert row["call_key"] == "ABC|2026-08-01" and row["source"] == "model" and row["cause"] == "news_after"


def test_a_bad_answer_leaves_the_code_line_so_the_call_still_gets_its_row(monkeypatch):
    for bad in (good(why_bn="No Bengali."), good(why_en="It fell 77 points."), good(evidence=["news:9"]),
                good(evidence=[]), good(cause="luck"), "not json"):
        w = W()
        go(w, bad, monkeypatch)
        (row,) = w.rows
        assert row["source"] == "code" and row["cause"] == "unknown" and row["why_bn"]
        assert not w.cache


def test_the_brief_is_public_only_and_the_checks_read_it():
    b = build(DUE)
    assert verify(good(), b)[1] == [] and "holding" not in json.dumps(b)
    try:
        build({**DUE, "reasons": [], "risks": [], "tax": 1, "key": "k"})
    except PrivateField:
        raise AssertionError("tax is not a brief key here; only reasons and risks are carried") from None
    assert "behind" in code_row(b)["why_en"]


def test_nothing_due_writes_nothing(monkeypatch):
    w = W({"calls": []})
    go(w, good(), monkeypatch)
    assert w.rows == []
