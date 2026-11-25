"""R14: gather each source on its own clock (store what arrives, retry only the missing), then one crunch."""
import json
from datetime import date, datetime

from fake_model import fake_analyse
from fakes import make_machine, settle
from stockpilot.jobs import daily, due
from test_jobs import fetch, fetch_json
from test_late_nse import no_bhavcopy
from test_screen import AS_OF, build

FRIDAY = date(2026, 11, 20)


def evening(hour, minute=0, day=FRIDAY):
    return datetime(day.year, day.month, day.day, hour, minute)


def machine(tmp_path, now, **kw):
    return make_machine(tmp_path, now=now, **kw)


def done(m, day=FRIDAY):
    with m.db("t") as db:
        return due.read_state(db, m.clock(), m.root).gathered


def recording(urls):
    def get(url):
        urls.append(url)
        return fetch(url)
    return get


def test_a_failing_source_is_a_problem_and_never_stops_the_others(tmp_path):
    def broken_bse(url):
        if "bseindia" in url:
            raise ConnectionError("BSE down")
        return fetch(url)

    m = machine(tmp_path, evening(17), fetch=broken_bse)
    out = daily.gather(m, m.clock())
    assert out["status"] == "partial" and "bse_prices" in out["failed"]
    got = done(m)
    assert "bse_prices" not in got and {"nse_prices", "indices", "deals", "filings", "docs"} <= got
    with m.db("t") as db:
        assert db.execute("select job, key from problems").fetchall() == [("daily_ingest", "bse_prices")]


def test_a_retry_runs_only_the_missing_sources(tmp_path):
    state = {"bse_up": False}

    def flaky(url):
        if "bseindia" in url and not state["bse_up"]:
            raise ConnectionError("BSE down")
        return fetch(url)

    m = machine(tmp_path, evening(17), fetch=flaky)
    daily.gather(m, m.clock())
    state["bse_up"] = True
    urls = []
    m2 = machine(tmp_path, evening(17, 5), fetch=lambda u: (urls.append(u), flaky(u))[1],
                 fetch_json=lambda p: (urls.append(p), fetch_json(p))[1])
    daily.gather(m2, m2.clock())
    assert len(urls) == 1 and "bseindia" in urls[0]                  # nothing already gathered was fetched again
    assert "bse_prices" in done(m2)
    assert daily.gather(m2, m2.clock())["pending"] == []             # and now there is nothing left to run


def test_nse_not_published_is_not_done_and_not_a_problem_and_other_sources_are_in(tmp_path):
    m = machine(tmp_path, evening(17), fetch=no_bhavcopy)
    out = daily.gather(m, m.clock())
    assert out["status"] == "waiting"
    got = done(m)
    assert "nse_prices" not in got and {"bse_prices", "indices", "deals"} <= got
    with m.db("t") as db:
        assert db.execute("select count(*) from problems").fetchone()[0] == 0
        assert due.due(due.read_state(db, m.clock(), m.root), evening(19, 30)) == ["queue", "gather"]


def test_when_nse_arrives_the_next_gather_fetches_it_and_the_crunch_becomes_due(tmp_path):
    m = machine(tmp_path, evening(17), fetch=no_bhavcopy)
    daily.gather(m, m.clock())
    m2 = machine(tmp_path, evening(19, 35))
    daily.gather(m2, m2.clock())
    with m2.db("t") as db:
        assert due.due(due.read_state(db, m2.clock(), m2.root), m2.clock()) == ["queue", "crunch"]


def test_no_worker_means_kite_is_simply_done(tmp_path):
    m = machine(tmp_path, evening(17), worker=None)
    daily.gather(m, m.clock())
    assert {"kite"} <= done(m)


# ---- the crunch ---------------------------------------------------------------------------------------

def stale_setup(tmp_path):
    """Calls exist for AS_OF; the next trading evening NSE has not published."""
    db = build(tmp_path)
    for name in due.GATHER_SOURCES:
        db.execute("insert into fetch_log values ('gathered', ?)", [f"{AS_OF}:{name}"])
    db.close()
    answers = {"analyst": {"GOOD": 0.70, "MEH": 0.60, "BAD": 0.30}, "skeptic": {"MEH": 0.66}}
    first = machine(tmp_path, datetime(2026, 6, 30, 20, 0), extra="store:\n  path: sp.duckdb\n", analyse=fake_analyse(answers, []))
    assert daily.crunch(first, first.clock())["status"] == "ok"
    settle(first)
    seen = []

    def analyse(*a, **k):
        seen.append(1)
        raise AssertionError("decide must not run on a day that already has calls")

    late = machine(tmp_path, datetime(2026, 7, 1, 22, 5), extra="store:\n  path: sp.duckdb\n", analyse=analyse,
                   fetch=no_bhavcopy)
    return late, seen


def test_a_stale_day_crunch_does_not_duplicate_calls_and_labels_the_page(tmp_path):
    late, seen = stale_setup(tmp_path)
    with late.db("t") as db:
        before = db.execute("select count(*), max(id) from calls").fetchone()
    daily.gather(late, late.clock())
    out = daily.crunch(late, late.clock())
    settle(late)
    assert out["status"] == "partial" and out["stale"] and out["calls_from"] == str(AS_OF) and not seen
    with late.db("t") as db:
        assert db.execute("select count(*), max(id) from calls").fetchone() == before          # calls untouched
        status, notes = db.execute("select status, notes from runs where job = 'crunch' order by id desc").fetchone()
        assert status == "partial" and json.loads(notes)["stale"] is True
        assert due.due(due.read_state(db, late.clock(), late.root), late.clock())[1:] == ["gather"]   # no second stale crunch
    meta = json.loads((tmp_path / "site" / "data" / "meta.json").read_text())
    assert meta["calls_on"] == str(AS_OF)
    assert meta["status"]["ok"] is False
    assert "Calls are from" in meta["status"]["text"] and "today's prices were not out" in meta["status"]["text"]
    assert "up to date" not in meta["status"]["text"]
    today = json.loads((tmp_path / "site" / "data" / "today.json").read_text())
    assert today["calls_note"] == meta["calls_note"] and "Calls are from" in today["calls_note"]
    assert "ship" in out and late.log.count("deploy") == 1


def test_the_status_text_is_up_to_date_only_when_the_calls_are_current(tmp_path):
    db = build(tmp_path)
    m = machine(tmp_path, datetime(2026, 6, 30, 20, 0), extra="store:\n  path: sp.duckdb\n",
                analyse=fake_analyse({"analyst": {"GOOD": 0.7, "MEH": 0.6, "BAD": 0.3}, "skeptic": {}}, []))
    db.close()
    for name in due.GATHER_SOURCES:
        with m.db("t") as d:
            d.execute("insert into fetch_log values ('gathered', ?)", [f"{AS_OF}:{name}"])
    daily.crunch(m, m.clock())
    meta = json.loads((tmp_path / "site" / "data" / "meta.json").read_text())
    assert "calls_note" not in meta["status"] or not meta["status"].get("calls_note")
    assert "Calls are from" not in meta["status"]["text"]
