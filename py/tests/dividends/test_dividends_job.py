import io
import json
import sys

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "runtime"))
from fake_runtime_worker import KEY, FakeRuntimeWorker

from stockpilot.io import Door
from stockpilot.jobs import dividends as dv
from stockpilot.runtime import run_job


def chart(*events):
    return {"chart": {"result": [{"events": {"dividends": {str(t): {"date": t, "amount": a} for t, a in events}}}]}}


def go(feed):
    w = FakeRuntimeWorker()
    posted = []
    orig = w.transport

    def transport(method, url, headers, body):
        if url.endswith("/api/money/held-symbols"):
            return 200, {"symbols": ["AAA", "BBB"], "since": "2024-01-01"}
        if url.endswith("/api/money/dividends"):
            posted.append(json.loads(body))
            return 200, {"stored": 1}
        return orig(method, url, headers, body)

    def fetch_json(url):
        return feed(url)

    run_job("dividends", lambda ctx: dv.run(ctx, fetch_json=fetch_json), door=Door("https://x.invalid", KEY, transport),
            day="2026-11-28", out=io.StringIO())
    return w, posted


def test_posts_dividends_of_each_stock_and_publishes_a_summary():
    w, posted = go(lambda url: chart((1752537600, 3.5)) if "AAA" in url else chart())
    assert posted == [{"symbol": "AAA", "rows": [{"ex_date": "2025-07-15", "per_share": 3.5}]}]
    assert [(r["symbols"], r["rows"]) for r in w.rows["dividends"].values()] == [(2, 1)]


def test_a_feed_that_fails_is_skipped_but_all_failing_fails_the_run():
    def feed(url):
        if "BBB" in url:
            raise OSError("down")
        return chart()
    go(feed)
    with pytest.raises(RuntimeError, match="no dividend feed"):
        go(lambda url: (_ for _ in ()).throw(OSError("down")))
