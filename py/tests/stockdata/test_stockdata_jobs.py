import io
import json
import sys
from datetime import date

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "runtime"))
from fake_runtime_worker import KEY, FakeRuntimeWorker  # noqa: E402

from stockpilot.io import Door  # noqa: E402
from stockpilot.jobs import history as hist  # noqa: E402
from stockpilot.jobs import universe as uni  # noqa: E402
from stockpilot.runtime import run_job  # noqa: E402


def entry(symbol, name="Co", exchange="NSE"):
    return {"symbol": symbol, "exchange": exchange, "segment": exchange, "name": name, "isin": "", "aliases": [name.lower(), symbol.lower()]}


def test_universe_keeps_a_stock_that_dropped_off_the_lists_as_delisted():
    prev = [{"id": "NSE:GONE", "symbol": "GONE", "exchange": "NSE", "segment": "NSE", "name": "Gone Co", "isin": "", "aliases": "gone co|gone", "status": "listed"},
            {"id": "NSE:OLDCO", "symbol": "OLDCO", "exchange": "NSE", "segment": "NSE", "name": "Old Name", "isin": "", "aliases": "old name|oldco", "status": "listed"}]
    rows = {r["id"]: r for r in uni.to_rows([entry("NEWCO", "New Name"), entry("KEEP")], prev)}
    assert rows["NSE:GONE"]["status"] == "delisted"
    assert rows["NSE:OLDCO"]["status"] == "delisted"          # a rename keeps the old name searchable
    assert rows["NSE:NEWCO"]["status"] == "listed" and rows["NSE:KEEP"]["status"] == "listed"


def test_a_move_over_40_percent_with_no_explanation_is_held_back():
    rows = [{"date": date(2026, 1, 1), "close": 100.0}, {"date": date(2026, 1, 2), "close": 50.0}]
    assert hist.unexplained_move(rows)["date"] == "2026-01-02"
    assert hist.unexplained_move(rows, {"2026-01-02"}) is None


def test_daily_hold_back_uses_the_exchanges_prev_close_so_a_split_does_not_trip_it():
    split = {"date": date(2026, 1, 2), "close": 20.0, "prev_close": 20.5}      # prev_close already corrected on the ex-date
    jump = {"date": date(2026, 1, 2), "close": 50.0, "prev_close": 100.0}
    good, held = hist.hold_back({("NSE", "SPLIT"): [split], ("NSE", "JUMP"): [jump]})
    assert list(good) == [("NSE", "SPLIT")] and list(held) == ["NSE:JUMP"]


def test_loading_a_symbol_posts_its_history(monkeypatch):
    chart = {"chart": {"result": [{"timestamp": [1767225600, 1767312000], "indicators": {"quote": [
        {"open": [1, 2], "high": [1, 2], "low": [1, 2], "close": [10.0, 11.0], "volume": [5, 6]}]}}]}}
    w = FakeRuntimeWorker()
    posted = []
    orig = w.transport

    def transport(method, url, headers, body):
        if url.endswith("/api/stocks/history"):
            posted.append(json.loads(body))
            return 200, {"stored": 2}
        return orig(method, url, headers, body)

    run_job("history", lambda ctx: hist.run(ctx, fetch_json=lambda url: chart), door=Door("https://x.invalid", KEY, transport),
            subject="NEWCO", day="2026-11-28", out=io.StringIO())
    assert posted[0]["symbol"] == "NEWCO" and posted[0]["exchange"] == "NSE"
    assert [r["close"] for r in posted[0]["rows"]] == [10.0, 11.0] and posted[0]["rows"][1]["prev_close"] == 10.0


def test_a_symbol_with_no_history_fails_the_load():
    w = FakeRuntimeWorker()
    with pytest.raises(RuntimeError, match="no price history"):
        run_job("history", lambda ctx: hist.run(ctx, fetch_json=lambda url: None), door=Door("https://x.invalid", KEY, w.transport),
                subject="NOPE", day="2026-11-28", out=io.StringIO())


def test_the_daily_run_posts_good_stocks_holds_back_a_jump_and_publishes_its_summary(monkeypatch):
    rows = {("NSE", "OK"): [{"date": date(2026, 11, 27), "close": 10.0, "prev_close": 9.5}],
            ("NSE", "JUMP"): [{"date": date(2026, 11, 27), "close": 50.0, "prev_close": 100.0}]}
    monkeypatch.setattr(hist, "daily_rows", lambda fetch, today, lookback=5: rows)
    monkeypatch.setattr(hist, "HELD_BACK_LIMIT", 0.6)
    w = FakeRuntimeWorker()
    posted = []
    orig = w.transport

    def transport(method, url, headers, body):
        if url.endswith("/api/stocks/history"):
            posted.append(json.loads(body)["symbol"])
            return 200, {"stored": 1}
        return orig(method, url, headers, body)

    run_job("history", lambda ctx: hist.run(ctx, fetch=lambda url: None), door=Door("https://x.invalid", KEY, transport),
            subject="history", day="2026-11-27", out=io.StringIO())
    assert posted == ["OK"]
    assert [(r["stocks"], r["held_back"]) for r in w.rows["history"].values()] == [(1, 1)]
