"""M16: the screen is computed once per trading day and stored; every reader takes the stored one."""
import json
from datetime import datetime

import pytest

from seed_site import AS_OF as SITE_DAY, seed
from test_screen import AS_OF, build

from stockpilot import site

from stockpilot.analysis import analytics, screen


@pytest.fixture
def counted(monkeypatch):
    calls = []
    real = analytics.price_factors

    def counting(*a, **k):
        calls.append(a[1])
        return real(*a, **k)
    monkeypatch.setattr(analytics, "price_factors", counting)
    return calls


def test_the_second_run_reads_the_stored_screen(tmp_path, counted):
    db = build(tmp_path)
    first = screen.run(db, AS_OF, 1.0)
    second = screen.run(db, AS_OF, 1.0)
    assert counted == [AS_OF] and first == second
    assert db.execute("select count(*), min(as_of) from screens").fetchone() == (1, AS_OF)


def test_the_stored_screen_is_what_a_fresh_run_would_give(tmp_path):
    db = build(tmp_path)
    fresh = screen.run(db, AS_OF, 1.0, fresh=True)
    stored = screen.run(db, AS_OF, 1.0)
    assert json.loads(json.dumps(stored, default=str)) == json.loads(json.dumps(fresh, default=str))
    assert isinstance(stored["as_of"], type(AS_OF))


def test_fresh_recomputes_and_replaces(tmp_path, counted):
    db = build(tmp_path)
    screen.run(db, AS_OF, 1.0)
    db.execute("insert or replace into fundamentals values (?, 'BAD', 'roe', 0.4, 'test')", [AS_OF])
    screen.run(db, AS_OF, 1.0, fresh=True)
    assert len(counted) == 2 and db.execute("select count(*) from screens").fetchone()[0] == 1


def test_another_floor_or_weights_do_not_read_the_stored_one(tmp_path, counted):
    db = build(tmp_path)
    screen.run(db, AS_OF, 1.0)
    screen.run(db, AS_OF, 5.0)
    screen.run(db, AS_OF, 1.0, weights={"quality": 1.0, "value": 0, "momentum": 0, "risk": 0})
    assert len(counted) == 3


def test_two_site_builds_compute_the_screen_once(tmp_path, counted):
    db = seed(tmp_path / "sp.duckdb")
    for name in ("a", "b"):
        site.build(db, tmp_path / name, today=SITE_DAY, now=datetime(2026, 11, 20, 19, 30))
    assert len(counted) == 1


def test_old_screens_are_dropped(tmp_path):
    db = build(tmp_path)
    for day in ("2026-01-01", "2026-02-01"):
        db.execute("insert into screens values (?, '{}')", [day])
    screen.run(db, AS_OF, 1.0)
    assert [str(d) for (d,) in db.execute("select as_of from screens").fetchall()] == [str(AS_OF)]


def test_the_site_reads_every_chart_in_one_query(tmp_path, monkeypatch):
    db = seed(tmp_path / "sp.duckdb")
    monkeypatch.setattr(analytics, "adjusted_closes", lambda *a, **k: pytest.fail("one query per stock"))
    seen = []
    real = analytics.adjusted_closes_many
    monkeypatch.setattr(analytics, "adjusted_closes_many", lambda db_, symbols, *a, **k: seen.append(len(set(symbols))) or real(db_, symbols, *a, **k))
    site.build(db, tmp_path / "out", today=SITE_DAY, now=datetime(2026, 11, 20, 19, 30))
    # the watchlist's averages, then the stock files a chunk of symbols at a time: never one query per stock
    assert len(seen) <= 4 and max(seen) > 100         # 125 stocks: the watchlist, two NSE chunks, one NYSE stock
    assert (tmp_path / "out" / "data" / "history" / "TCS.json").exists()


def test_adjusted_closes_many_equals_one_at_a_time(tmp_path):
    db = seed(tmp_path / "sp.duckdb")
    since = SITE_DAY.replace(year=2025)
    many = analytics.adjusted_closes_many(db, ["TCS", "INFY", "NOPE"], since)
    assert many["TCS"] == analytics.adjusted_closes(db, "TCS", since)
    assert many["INFY"] == analytics.adjusted_closes(db, "INFY", since)
    assert many["NOPE"] == []
