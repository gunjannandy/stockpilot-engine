"""C-040-4: the backfill gives every listed fixture stock its full history; a series with an unexplained jump is held back
with its reason, and the run passes below the threshold."""
from datetime import date, datetime, timezone

import pytest

from stockpilot.jobs import history as hist

TODAY = date(2026, 11, 27)


class Ctx:
    class client:  # noqa: N801
        posts: list = []

        @classmethod
        def _ok(cls, path, body=None, method="POST"):
            cls.posts.append((body["symbol"], len(body["rows"])))
            return {}

    class progress:  # noqa: N801
        lines: list = []

        @classmethod
        def line(cls, text, *a):
            cls.lines.append(text)


def _chart(closes):
    ts = [int(datetime(2000, 1, 3 + i, tzinfo=timezone.utc).timestamp()) for i in range(len(closes))]
    return {"chart": {"result": [{"timestamp": ts, "indicators": {"quote": [
        {"open": closes, "high": closes, "low": closes, "close": closes, "volume": [1] * len(closes)}]}}]}}


def _stocks(n):
    return [{"id": f"NSE:S{i}", "symbol": f"S{i}", "exchange": "NSE", "status": "listed"} for i in range(n)]


def setup_function():
    Ctx.client.posts, Ctx.progress.lines = [], []


def test_every_listed_stock_gets_its_full_history_and_delisted_is_skipped():
    stocks = _stocks(100) + [{"id": "NSE:OLD", "symbol": "OLD", "exchange": "NSE", "status": "delisted"}]
    loaded, held = hist.backfill_all(Ctx, stocks, lambda url: _chart([10, 11, 12, 13]), TODAY)
    assert loaded == 100 and not held and len(Ctx.client.posts) == 100
    assert all(n == 4 for _, n in Ctx.client.posts)


def test_unexplained_jump_is_held_back_with_reason_and_run_passes_below_threshold():
    def fetch(url):
        return _chart([10, 30, 31]) if "/S7.NS?" in url else _chart([10, 11, 12])
    loaded, held = hist.backfill_all(Ctx, _stocks(100), fetch, TODAY)
    assert loaded == 99 and list(held) == ["NSE:S7"]
    assert held["NSE:S7"] == {"date": "2000-01-04", "from": 10, "to": 30}
    assert all(s != "S7" for s, _ in Ctx.client.posts)


def test_run_fails_when_too_many_are_held_back():
    with pytest.raises(RuntimeError):
        hist.backfill_all(Ctx, _stocks(10), lambda url: _chart([10, 30]), TODAY)
