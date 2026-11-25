"""A late NSE file is `waiting`, not `failed`; holidays stay holidays; step problems are keyed by step name."""
import json
from datetime import date

from stockpilot import cli, store
from stockpilot.jobs import daily
from fakes import without_bhavcopy
from test_jobs import fetch, fetch_json

no_bhavcopy = without_bhavcopy(fetch)

TRADING_DAY = date(2026, 11, 20)


def test_a_trading_day_with_no_bhavcopy_is_waiting_not_failed(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    report = daily.daily_ingest(db, TRADING_DAY, no_bhavcopy, fetch_json)
    assert report["status"] == "waiting"
    status, notes = db.execute("select status, notes from runs where job = 'daily_ingest'").fetchone()
    assert status == "waiting"
    assert json.loads(notes)["note"] == "NSE has not published 2026-11-20 yet"
    assert db.execute("select count(*) from problems").fetchone()[0] == 0       # nothing to put on the Health tab yet


def test_the_other_sources_still_load_while_nse_is_late(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    report = daily.daily_ingest(db, TRADING_DAY, no_bhavcopy, fetch_json)
    assert report["counts"]["bse_prices"] == 6 and report["counts"]["nse_prices"] == 0


def test_a_holiday_by_the_calendar_stays_a_holiday_even_though_nse_404s(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    report = daily.daily_ingest(db, date(2026, 11, 24), no_bhavcopy, fetch_json)
    assert report["status"] == "holiday"
    assert db.execute("select status from runs where job = 'daily_ingest'").fetchone()[0] == "holiday"


def test_an_error_while_fetching_prices_is_still_failed(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")

    def down(url):
        if "NSE_CM" in url:
            raise ConnectionError("NSE down")
        return fetch(url)

    assert daily.daily_ingest(db, TRADING_DAY, down, fetch_json)["status"] == "failed"


def test_a_problem_is_keyed_by_step_and_the_traceback_is_in_the_run_notes(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")

    def broken_bse(url):
        if "bseindia" in url:
            raise ConnectionError("BSE down")
        return fetch(url)

    daily.daily_ingest(db, TRADING_DAY, broken_bse, fetch_json)
    [(key, message)] = db.execute("select key, message from problems").fetchall()
    assert key == "bse_prices"
    assert "BSE down" in message and "Traceback" not in message and "\n" not in message
    notes = json.loads(db.execute("select notes from runs where job = 'daily_ingest'").fetchone()[0])
    assert "Traceback" in notes["tracebacks"]["bse_prices"] and "BSE down" in notes["tracebacks"]["bse_prices"]


def test_a_repeated_failure_bumps_one_problem(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")

    def broken_bse(url):
        if "bseindia" in url:
            raise ConnectionError("BSE down")
        return fetch(url)

    daily.daily_ingest(db, TRADING_DAY, broken_bse, fetch_json)
    daily.daily_ingest(db, TRADING_DAY, broken_bse, fetch_json)
    assert db.execute("select count(*), max(count) from problems").fetchone() == (1, 2)


def _machine(tmp_path, **kw):
    from datetime import datetime
    from fakes import make_machine
    return make_machine(tmp_path, now=datetime(2026, 11, 20, 20, 3), fetch=no_bhavcopy, fetch_json=fetch_json, **kw)


def test_daily_stops_at_waiting_and_skips_decide_and_ship(tmp_path):
    m = _machine(tmp_path, analyse=lambda *a: (_ for _ in ()).throw(AssertionError("decide ran")),
                 deploy=lambda: (_ for _ in ()).throw(AssertionError("deploy ran")))
    report = daily.run(m, m.clock())
    assert report["status"] == "waiting" and "decide" not in report and "ship" not in report


def test_cmd_daily_exits_75_on_waiting(tmp_path, monkeypatch):
    m = _machine(tmp_path)
    monkeypatch.setattr(cli, "_machine", lambda cfg, job="tick": m)
    assert cli.main(["--root", str(tmp_path), "daily", "--date", "2026-11-20"]) == 75
