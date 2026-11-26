"""Deploy order (lane P2): build the site, `sp verify` with write access (it writes the price flags), rebuild, verify again, then deploy.
Only the second verify gates the deploy: the first one is what writes the flags the rebuilt site hides."""
from datetime import datetime

from fakes import make_machine
from seed_site import seed as seed_site
from stockpilot.jobs import ship

NOW = datetime(2026, 11, 20, 20, 0)


def machine(tmp_path, **kw):
    seed_site(tmp_path / "data" / "stockpilot.duckdb").close()
    return make_machine(tmp_path, now=datetime(2026, 11, 22, 23, 33), **kw)


def run_ship(tmp_path, monkeypatch, outcomes, **kw):
    m = machine(tmp_path, **kw)
    log = m.log
    real_build = ship.build_site
    monkeypatch.setattr(ship, "build_site", lambda *a, **k: log.append("build") or real_build(*a, **k))
    it = iter(outcomes)

    def fake_verify(mm, day, *, write=True):
        log.append("verify" if write else "verify-read-only")
        return next(it)
    monkeypatch.setattr(ship, "run_verify", fake_verify)
    with m.db("ship") as db:
        out = ship.ship(m, db, NOW)
    return m, out


PASS = {"hard_failed": 0, "summary": "0 failed"}
FAIL = {"hard_failed": 2, "summary": "2 hard failures"}


def test_ship_builds_verifies_with_write_access_rebuilds_verifies_again_then_deploys(tmp_path, monkeypatch):
    m, out = run_ship(tmp_path, monkeypatch, [FAIL, PASS])
    assert m.log == ["build", "verify", "build", "verify", "push_status", "push_archive", "deploy"]
    assert out["deploy"] == "Dashboard deployed."


def test_the_first_pass_never_blocks_only_the_final_one_does(tmp_path, monkeypatch):
    m, out = run_ship(tmp_path, monkeypatch, [FAIL, FAIL])
    assert "deploy" not in m.log
    assert "held back" in out["deploy"] and "2 hard failures" in out["deploy"]
    with m.db("t") as db:
        assert db.execute("select count(*) from problems where job = 'ship' and message like '%held back%'").fetchone()[0] == 1


def test_a_verify_that_cannot_run_is_a_problem_but_does_not_freeze_the_dashboard(tmp_path, monkeypatch):
    m = machine(tmp_path)

    def boom(mm, day, *, write=True):
        raise RuntimeError("the store is busy")
    monkeypatch.setattr(ship, "run_verify", boom)
    with m.db("ship") as db:
        out = ship.ship(m, db, NOW)
    assert out["deploy"] == "Dashboard deployed."
    with m.db("t") as db:
        assert db.execute("select count(*) from problems where job = 'ship' and message like '%verify%'").fetchone()[0] >= 1


def test_it_can_be_switched_off_in_config(tmp_path, monkeypatch):
    m = machine(tmp_path, extra="verify:\n  on_ship: false\n")
    monkeypatch.setattr(ship, "run_verify", lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not run")))
    with m.db("ship") as db:
        out = ship.ship(m, db, NOW)
    assert out["deploy"] == "Dashboard deployed."


def test_the_database_is_let_go_before_each_verify(tmp_path, monkeypatch):
    m = machine(tmp_path)
    held = []

    def fake_verify(mm, day, *, write=True):
        held.append(db.held)          # `sp verify` opens the store for writing itself, so this handle must be free
        return PASS
    monkeypatch.setattr(ship, "run_verify", fake_verify)
    with m.db("ship") as db:
        ship.ship(m, db, NOW)
    assert held == [False, False]


def test_run_verify_calls_sp_verify_with_write_access_and_returns_the_hard_failure_count(tmp_path, monkeypatch):
    from stockpilot.verify import run as verify_run
    m = machine(tmp_path)
    seen = {}

    def fake_run(cfg, **kw):
        seen.update(kw)
        kw["out"].write("verify: 0 failed\n")
        return 0
    monkeypatch.setattr(verify_run, "run", fake_run)
    got = ship.run_verify(m, NOW.date())
    assert seen["read_only"] is False and seen["db_path"] == m.db_path and seen["site"] == m.root / "site"
    assert got["hard_failed"] == 0 and "verify" in got["summary"]


def test_build_site_ships_the_public_data_files_when_configured(tmp_path, monkeypatch):
    """The browser cannot read release assets, so the deploy carries the public files (docs/contract/live-data-v2.md)."""
    from datetime import date
    from stockpilot import config
    from stockpilot.sources import public_files
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "stockpilot.yaml").write_text("worker:\n  url: https://x.pages.dev\npublic_data:\n  repo: o/r\n")
    seen = []
    monkeypatch.setattr(public_files, "fetch_into", lambda site, repo, **k: seen.append((str(site), repo)) or [])
    ship.build_site(seed_site(tmp_path / "sp.duckdb"), config.load(tmp_path), today=date(2026, 11, 22))
    assert seen == [(str(tmp_path / "site"), "o/r")]


def test_a_broken_public_fetch_does_not_stop_the_build(tmp_path, monkeypatch):
    from datetime import date
    from stockpilot import config
    from stockpilot.sources import public_files
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "stockpilot.yaml").write_text("worker:\n  url: https://x.pages.dev\npublic_data:\n  repo: o/r\n")
    def boom(*a, **k): raise RuntimeError("down")
    monkeypatch.setattr(public_files, "fetch_into", boom)
    meta = ship.build_site(seed_site(tmp_path / "sp.duckdb"), config.load(tmp_path), today=date(2026, 11, 22))
    assert meta is not None
