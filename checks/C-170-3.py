"""C-170-1 (Job half): the forecast Job holds a bad call back, reports it, adds "limited evidence", and fails past a threshold."""
import json
from datetime import date

import pytest

from stockpilot.jobs.forecast import make_calls, run, screen_and_hold

REPORT = {"horizons": {"63": {"n_test": 500, "hit_rate": 0.52}}}


def res(symbol, chance, low=90.0, high=120.0):
    return {"symbol": symbol, "exchange": "NSE", "chance_3m": chance, "low_3m": low, "likely_3m": 100.0, "high_3m": high}


def test_chance_outside_the_band_is_held_back_and_the_rest_go():
    rows = make_calls([res("A", 0.6), res("B", 0.97), res("C", 0.02)], REPORT, date(2026, 11, 28), [], {})
    ok, held = screen_and_hold(rows)
    assert [r["symbol"] for r in ok] == ["A"] and len(held) == 2


def test_thin_base_rate_holds_nothing_back_but_adds_limited_evidence_then_check_fails_without_it():
    thin = {"horizons": {"63": {"n_test": 12, "hit_rate": 0.5}}}
    rows = make_calls([res("A", 0.6)], thin, date(2026, 11, 28), [], {})
    assert screen_and_hold(rows)[1]    # fewer than 30 cases: held back
    moved = make_calls([res("A", 0.6)], {"horizons": {"63": {"n_test": 500, "hit_rate": 0.62}}}, date(2026, 11, 28), [], {63: 0.50})
    assert moved[0]["limited"] and any("limited evidence" in s["en"].lower() for s in json.loads(moved[0]["sentences_json"]))
    assert screen_and_hold(moved)[1] == []


def test_no_view_is_a_call_without_a_chance():
    rows = make_calls([res("A", None, None, None)], REPORT, date(2026, 11, 28), [], {})
    assert rows[0]["verdict"] == "No view yet" and screen_and_hold(rows)[1] == []


class Ctx:
    def __init__(self):
        from datetime import date as d
        self.range = type("R", (), {"end": d(2026, 11, 28)})()
        self.sent = []
        self.progress = type("P", (), {"line": lambda s, *a, **k: None})()
        self.client = self
        self.published = []

    def _ok(self, path, payload=None, method="POST"):
        self.sent.append(path)
        return {"written": len(payload["rows"]), "ignored": 0}

    def publish(self, *a, **k):
        self.published.append(a[0])


def test_run_sends_good_calls_and_fails_past_the_threshold():
    ctx = Ctx()
    out = run(ctx, [res(f"S{i}", 0.6) for i in range(20)], REPORT, [], {})
    assert "20 calls added" in out and ctx.published == ["calls_runs"]
    with pytest.raises(RuntimeError):
        run(Ctx(), [res("A", 0.6), res("B", 0.99)], REPORT, [], {})
