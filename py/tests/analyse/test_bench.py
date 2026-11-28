import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from analyse_support import AnalyseWorker, answer_for, door  # noqa: E402

from stockpilot.jobs.bench import run, score  # noqa: E402
from stockpilot.runtime import run_job  # noqa: E402

ITEMS = score.cases()


class BenchWorker(AnalyseWorker):
    def __init__(self, status=None, **kw):
        super().__init__(**kw)
        self.status, self.reports = status or {"fingerprint": None, "comparison": None}, []

    def transport(self, method, url, headers, body):
        route = "/" + url.split("/", 3)[3]
        if route == "/api/bench/status":
            return 200, self.status
        if route == "/api/bench/report":
            self.reports.append(json.loads(body))
            return 200, {"ok": True}
        return super().transport(method, url, headers, body)


def by_code(prompt, model):
    # The prompt ends with the brief; find which case it is by its symbol.
    sym = json.loads(prompt.split("BRIEF:\n", 1)[1])["symbol"]
    case = next(c for c in ITEMS if c["brief"]["symbol"] == sym)
    return answer_for(case["brief"])


def go(w, ask):
    import io
    run_job("bench", lambda ctx: run(ctx, ask=ask), door=door(w), day="2026-11-28", out=io.StringIO())


def test_first_run_is_the_comparison_and_reports_green():
    w = BenchWorker()
    go(w, by_code)
    (r,) = w.reports
    assert r["comparison"]["passed"] and r["forecast_model"] == "haiku" and r["red"] == []
    assert r["scores"]["form_rate"] == 1.0


def test_an_unchanged_fingerprint_ends_without_asking_the_model():
    w = BenchWorker({"fingerprint": score.fingerprint(), "comparison": {"form_rate": 1, "agreement": 1, "passed": True,
                                                                          "forecast_model": "haiku"}})
    go(w, lambda *a: (_ for _ in ()).throw(AssertionError("must not ask")))
    assert w.reports == []


def test_broken_answers_make_the_bench_red():
    w = BenchWorker()
    go(w, lambda prompt, model: "not json")
    (r,) = w.reports
    assert r["red"] and r["scores"]["form_rate"] == 0 and r["forecast_model"] == "sonnet"


def test_the_fingerprint_changes_with_the_model_and_the_prompt(monkeypatch):
    base = score.fingerprint("haiku")
    assert base != score.fingerprint("sonnet")
    monkeypatch.setattr(score, "load", lambda name: "another prompt")
    assert score.fingerprint("haiku") != base


def test_a_model_trailing_the_code_only_hit_rate_is_red():
    s = {"form_rate": 1.0, "hit_rate": 0.4, "code_hit_rate": 0.6, "decided": 20}
    assert score.is_red(s)
    assert not score.is_red({**s, "hit_rate": 0.58})
