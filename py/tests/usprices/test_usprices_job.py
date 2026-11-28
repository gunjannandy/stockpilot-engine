import io
import json
import sys

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "runtime"))
from fake_runtime_worker import KEY, FakeRuntimeWorker

from stockpilot.io import Door
from stockpilot.jobs import usprices as up
from stockpilot.runtime import run_job


def chart(closes):
    ts = [1767225600 + 86400 * i for i in range(len(closes))]
    return {"chart": {"result": [{"timestamp": ts, "indicators": {"quote": [{"close": closes}]}}]}}


def go(series, symbols=("AAA", "BBB")):
    w = FakeRuntimeWorker()
    calls = []
    orig = w.transport

    def transport(method, url, headers, body):
        if url.endswith("/api/money/us-symbols"):
            return 200, {"symbols": list(symbols), "since": "2026-01-01", "fx_since": "2026-01-01"}
        if url.endswith("/api/money/fx-refresh"):
            calls.append(("fx", json.loads(body)))
            return 200, {"added": 3}
        if url.endswith("/api/money/us-prices"):
            calls.append(("prices", json.loads(body)))
            return 200, {"stored": 1}
        return orig(method, url, headers, body)

    def fetch_json(url):
        return series[next(s for s in series if s in url)]

    run_job("usprices", lambda ctx: up.run(ctx, fetch_json=fetch_json), door=Door("https://x.invalid", KEY, transport),
            day="2026-11-28", out=io.StringIO())
    return w, calls


def test_posts_each_symbol_asks_for_rates_and_holds_back_a_jump():
    w, calls = go({"AAA": chart([10.0, 11.0]), "BBB": chart([100.0, 40.0])})
    assert calls[0] == ("fx", {"since": "2026-01-01"})
    assert [c[1]["symbol"] for c in calls if c[0] == "prices"] == ["AAA"]
    assert [(r["symbols"], r["held_back"]) for r in w.rows["usprices"].values()] == [(1, 1)]


def test_fails_when_nothing_could_be_posted():
    with pytest.raises(RuntimeError, match="no prices posted"):
        go({"AAA": None, "BBB": None})
