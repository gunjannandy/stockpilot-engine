"""Seam 5 and 7: the daily pipeline in order (ingest, Kite, decide, brief on disk, site, deploy) and its run rows."""
import json
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from fake_worker import KEY, FakeWorker
from seed_site import seed as seed_site
from fake_model import fake_analyse, item as item_for
from test_jobs import fetch, fetch_json
from test_screen import AS_OF, build

from fakes import make_machine
from stockpilot import cli, config, store
from stockpilot.sources import kite
from stockpilot.jobs import daily, nav, ship, weekly
from stockpilot.trades import lots

KITE = {"holdings": [{"tradingsymbol": "GOOD", "isin": "INE000G01010", "quantity": 10, "t1_quantity": 0,
                      "average_price": 90.0}], "mf_holdings": [], "trades": [], "positions": {}, "margins": {}, "gtts": []}
NOW = datetime(AS_OF.year, AS_OF.month, AS_OF.day, 20, 0)


def cfg_in(tmp_path, extra=""):
    (tmp_path / "config").mkdir(exist_ok=True)
    (tmp_path / "config" / "stockpilot.yaml").write_text("worker:\n  url: https://stockpilot-2zl.pages.dev\n" + extra)
    return config.load(tmp_path)


def machine(tmp_path, worker=None, **kw):
    """A Machine over the store `build()` made, with prices already ingested for AS_OF and fake runners."""
    answers = {"analyst": {"GOOD": 0.70, "MEH": 0.60, "BAD": 0.30}, "skeptic": {"MEH": 0.66}}
    seen = []
    m = make_machine(tmp_path, now=NOW, extra="store:\n  path: sp.duckdb\n" + kw.pop("extra", ""), worker=worker,
                     analyse=fake_analyse(answers, seen), **kw)
    m.seen = seen
    return m


def ingested(db, day=AS_OF):
    """Every exchange source is in for `day` (R14: the crunch works on what gather stored)."""
    from stockpilot.jobs import due
    for name in due.GATHER_SOURCES:
        if name not in ("kite", "docs"):             # the exchange sources are in; Kite and documents still run
            db.execute("insert or replace into fetch_log values ('gathered', ?)", [f"{day}:{name}"])
    db.execute("insert into runs (job, started_at, finished_at, status) values ('daily_ingest', ?, ?, 'ok')",
               [datetime(day.year, day.month, day.day, 19, 5), datetime(day.year, day.month, day.day, 19, 6)])


def built(tmp_path):
    db = build(tmp_path)
    ingested(db)
    db.close()


@pytest.fixture
def worker():
    w = FakeWorker(kite=KITE)
    yield kite.Worker(w.url, KEY)
    w.close()


def test_kite_runs_before_the_decision_and_the_decision_sees_the_holding(tmp_path, worker):
    built(tmp_path)
    m = machine(tmp_path, worker)
    report = daily.run(m, NOW)
    assert report["status"] == "ok" and report["kite"]["holdings"] == 1
    with m.db("t") as db:
        assert [j for j, in db.execute("select job from runs order by id").fetchall()] == ["daily_ingest", "kite", "crunch", "daily_decide"]
    good = next(s for s in m.seen[0][1]["stocks"] if s["symbol"] == "GOOD")
    assert good["holding"]["qty"] == 10               # a Kite 'stock' holding counts as held


def test_a_kite_409_is_a_note_not_a_failure(tmp_path):
    w = FakeWorker(kite=None)
    try:
        built(tmp_path)
        m = machine(tmp_path, kite.Worker(w.url, KEY))
        report = daily.run(m, NOW)
    finally:
        w.close()
    assert report["status"] == "ok" and report["kite"]["status"] == "login_needed"
    with m.db("t") as db:
        status, notes = db.execute("select status, notes from runs where job = 'kite'").fetchone()
        assert status == "ok" and json.loads(notes)["login_needed"] is True
        assert db.execute("select count(*) from problems").fetchone()[0] == 0


def test_a_dead_worker_is_a_problem_and_the_decision_still_runs(tmp_path):
    built(tmp_path)
    m = machine(tmp_path, kite.Worker("http://127.0.0.1:9", KEY, timeout=1))
    report = daily.run(m, NOW)
    assert report["status"] == "ok" and report["kite"]["status"] == "failed"
    with m.db("t") as db:
        assert db.execute("select status from runs where job = 'kite'").fetchone()[0] == "failed"
        assert db.execute("select job from problems").fetchone()[0] == "kite"


def test_the_brief_is_saved_and_the_market_view_is_in_the_run_notes(tmp_path):
    built(tmp_path)
    m = machine(tmp_path)
    daily.run(m, NOW)
    saved = json.loads((tmp_path / "data" / "briefs" / f"{AS_OF}.json").read_text())
    assert [s["symbol"] for s in saved["stocks"]] == [s["symbol"] for s in m.seen[0][1]["stocks"]]
    assert "budget" not in json.dumps(saved).lower()
    with m.db("t") as db:
        notes = json.loads(db.execute("select notes from runs where job = 'daily_decide'").fetchone()[0])
    assert notes["market_view"] == "Calm."


def test_ingest_pulls_corporate_actions_and_restates_lots_around_a_split(tmp_path):
    db = store.open(tmp_path / "data" / "sp.duckdb")
    lots.save_trades(db, [lots.Trade("tradebook", "T1", "stock", "RELIANCE", "INE002A01018", "buy",
                                     date(2026, 1, 1), 10, 100)])
    lots.rebuild(db)
    report = daily.daily_ingest(db, date(2026, 11, 20), fetch, fetch_json)
    assert report["counts"]["corporate_actions"] == 2          # the dividend row is not an action
    assert db.execute("select quantity, cost_per_unit from lots").fetchone() == (20.0, 50.0)


def test_publish_builds_the_site_then_deploys(tmp_path):
    db = seed_site(tmp_path / "sp.duckdb")
    m = make_machine(tmp_path, deploy=lambda: (tmp_path / "site" / "data" / "today.json").exists() and "deployed")
    note = ship.publish(m, db, today=date(2026, 11, 22))      # built first, or the fake deploy returns False
    assert "deployed" in note


def test_wrangler_runs_from_web_to_the_project(tmp_path, monkeypatch):
    monkeypatch.setenv("WRANGLER", "/opt/npm/bin/wrangler")       # R16: called by absolute path, as the units set it
    cfg = cfg_in(tmp_path)
    calls = []

    def run(cmd, **kw):
        calls.append((cmd, kw["cwd"]))
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    assert "deployed" in ship.deploy_site(cfg, run)
    assert calls == [(["/opt/npm/bin/wrangler", "pages", "deploy", "../site", "--project-name", "stockpilot-2zl"], tmp_path / "web")]


def test_a_failed_deploy_is_logged_and_raised(tmp_path):
    db = seed_site(tmp_path / "sp.duckdb")
    m = make_machine(tmp_path, deploy=lambda: (_ for _ in ()).throw(RuntimeError("wrangler exited 1: not logged in")))
    with pytest.raises(RuntimeError, match="not logged in"):
        ship.publish(m, db, today=date(2026, 11, 22))
    assert db.execute("select count(*) from problems where job = 'deploy'").fetchone()[0] == 1


def test_the_health_tab_shows_token_countdowns_from_config(tmp_path):
    db = seed_site(tmp_path / "sp.duckdb")
    cfg = cfg_in(tmp_path, "tokens:\n  Claude login: {issued: '2026-10-01', lifetime_days: 365}\n")
    ship.build_site(db, cfg, today=date(2026, 11, 22))
    health = json.loads((tmp_path / "site" / "data" / "health.json").read_text())
    assert health["tokens"] == [{"name": "Claude login", "expires_on": "2027-10-01", "days_left": 313}]


def test_nav_rebuilds_and_deploys_and_ship_pushes_status_then_archive_then_deploys(tmp_path, monkeypatch):
    seed_site(tmp_path / "data" / "stockpilot.duckdb").close()
    m = make_machine(tmp_path, now=datetime(2026, 11, 22, 23, 33))
    monkeypatch.setattr("stockpilot.sources.funds.ingest_navall", lambda db, f: m.log.append("navs") or 12)
    assert nav.run(m, m.clock())["status"] == "ok"
    assert m.log == ["navs", "deploy"]
    m.log.clear()
    with m.db("ship") as db:
        out = ship.ship(m, db, datetime(2026, 11, 20, 20, 0))
    assert m.log == ["push_status", "push_archive", "deploy"] and out["deploy"] == "Dashboard deployed."
    with m.db("t") as db:
        assert ("nav", "ok") in db.execute("select job, status from runs").fetchall()
        # R4 x R2: a day the archive branch accepted is frozen in archived_days (the push itself has no database)
        assert [str(d) for d, in db.execute("select day from archived_days").fetchall()] == ["2026-11-20"]


def test_a_seeded_store_runs_daily_then_weekly_and_the_dashboard_shows_both(tmp_path, worker):
    """Daily (Kite, decide, brief, ship), the weekly analysis, then the site shows both."""
    db = seed_site(tmp_path / "data" / "stockpilot.duckdb")
    db.execute("delete from weekly_reports")
    ingested(db, date(2026, 11, 20))
    db.close()

    def analyse(brief, role, runners, **kw):
        return {"runner": "fake", "failures": [], "decisions": {"market_view": "Steady.", "market_view_bn": "স্থির।", "items": [
            item_for(s["symbol"], 0.5) for s in brief["stocks"]]}}
    m = make_machine(tmp_path, now=datetime(2026, 11, 20, 20, 0), worker=worker, analyse=analyse)
    assert daily.run(m, m.clock())["status"] == "ok"
    assert weekly.run(m, datetime(2026, 11, 21, 12, 0), analyse_only=True)["status"] == "ok"
    with m.db("t") as db:
        ship.build_site(db, m.cfg, today=date(2026, 11, 22))
    site = tmp_path / "site" / "data"
    page = json.loads((site / "portfolio.json").read_text())
    assert page["tax"]["fy"] == "2026-27" and page["tax"]["itr_pack"] == "downloads/tax-pack-2026-27.zip"
    assert page["opportunities"] and page["allocation"]["labels"]   # Kite holds no fund, so no fund review
    health = json.loads((site / "health.json").read_text())
    assert {"kite", "daily_decide", "weekly"} <= {r["job"] for r in health["runs"]}
    assert json.loads((site / "today.json").read_text())["market_mood"] == "Steady."
