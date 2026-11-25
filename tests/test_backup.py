"""Lane S: the database backup. Temp DBs, temp keys, injected uploader/downloader; no network, no gh."""
import json
from pathlib import Path

import pytest

from stockpilot import backup, config, journal, store, vault
from stockpilot.jobs import ship

PASSWORD = "correct horse"


@pytest.fixture(scope="module")
def keys():
    return vault.create_keys(PASSWORD)     # one scrypt derivation for the module


def seed(db):
    db.execute("insert into watchlist (symbol, exchange, added_by) values ('TCS', 'NSE', 'papa')")
    db.execute("insert into budgets (month, amount_inr, set_by) values ('2026-11', 100000, 'papa')")
    db.execute("insert into target_allocations (allocation, approved_by) values ('{\"stocks\": 60}', 'papa')")
    db.execute("insert into runs (job, status, notes) values ('daily', 'ok', '{\"k\": 1}')")
    db.execute("insert into calls (run_id, made_on, symbol, kind, action, reasons) "
               "values (1, '2026-11-20', 'TCS', 'stock', 'buy', '[\"cheap\"]')")
    db.execute("insert into requests (kind, payload, status) values ('budget_set', '{\"a\": 1}', 'done')")
    db.execute("insert into problems (job, severity, message) values ('daily', 'warning', 'x')")
    db.execute("insert into holdings values ('2026-11-20 10:00:00', 'stock', 'TCS', 'INE467B01029', 5, 3400.5, 'kite')")
    db.execute("insert into fund_calls (made_on, isin, scheme_code, name, category, call, code_call, line, detail) values "
               "('2026-11-21', 'INF1', 1, 'Fund 1', 'Equity Scheme - Flexi Cap Fund', 'Keep', 'Keep', 'Nothing to do.', '{}')")
    db.execute("insert into kite_syncs values ('2026-11-20 10:00:00', '[]', '[]', '{}', '[]')")
    db.execute("insert into trades (trade_key, source, kind, symbol, side, trade_date, quantity, price) "
               "values ('k1', 'tradebook', 'stock', 'TCS', 'buy', '2026-01-02', 5, 3400.5)")
    db.execute("insert into lots (kind, symbol, acquired_on, quantity, cost_per_unit) "
               "values ('stock', 'TCS', '2026-01-02', 5, 3400.5)")
    db.execute("insert into sales (kind, symbol, sold_on, quantity, price_per_unit) "
               "values ('stock', 'TCS', '2026-06-02', 1, 4000)")
    db.execute("insert into weekly_reports values ('2026-11-15', 'tax', '{\"gain\": 1}')")
    db.execute("insert into documents (id, source, kind, version, outcome) values ('m1', 'gmail', 'contract_note', '|4', 'parsed')")
    db.execute("insert into holding_statements values ('2026-10-31', 'INE467B01029', 5)")
    db.execute("insert into not_now (symbol, scope, until, set_by) values ('TCS', 'buy', '2026-12-01', 'papa')")
    db.execute("insert into archived_days (day) values ('2026-11-20')")
    db.execute("insert into feedback (author, kind, text, status, backlog_id) values ('papa', 'want', 'Bigger fonts', 'auto', 41)")
    db.execute("insert into learned_forgotten (pattern, until) values ('industry:Banks', '2027-02-01')")
    db.execute("insert into smallcase_orders values ('o1', 'Value', '2026-11-08', 'INFOSYS', 'buy', 10, 1500.5, 'm9')")
    db.execute("insert into trade_tags values ('t1', 'smallcase', 'Value', 'mail')")
    db.execute("insert into payslip_perquisites values ('payslip', '2023-02', 120000, 'd1')")
    db.execute("insert into action_terms values ('PARENT', '2023-07-20', 'demerger', 'INE000C01010', 'CHILD', 0.1, null)")
    db.execute("insert into console_pnl_totals values ('2025-26', 'equity', 'short_term', -100.5, '2026-03-21', 'd1', '2026-03-21')")
    db.execute("insert into console_pnl values ('2025-26', 'equity', 'short_term', 'TCS', 'INE467B01029', 1, 10, 7, -3, 'd1')")
    db.execute("insert into itr_documents values ('r1', 'return', '2026-27', '2025-26', 'ITR-2', '2026-07-11', true, true, 0, "
               "'m1', 2612465, 653617, 609, 654225, 0, 0, 14986, -50202, -45202, 58188, 60188, 646865)")
    db.execute("insert into feedback_changes values ('2026-11-20', '[\"Planned: bigger fonts\"]')")
    db.execute("insert into fidelity_events values ('f1', 'vest', '2025-02-14', '22RUIN13', 7, 5, 790.25, 3951.25, null, null)")
    db.execute("insert into fidelity_holdings values ('2026-11-24', 'NOW', 'US81762P1021', 339, 4479761.57, 2874999.61, 91.28)")
    db.execute("insert into fidelity_lots values ('2025-12-31', 'NOW', 'US81762P1021', '2025-11-17', 20, 300000, 15000, 277000, -23000, '2025-11-17', '2023-03-15', 'short')")
    db.execute("insert into gaps (area, subject, reason, detail) values ('price_history', 'IGARASHI', 'not_collected', 'no history')")
    # market data
    db.execute("insert into prices values ('2026-11-20', 'TCS', 'NSE', 'EQ', 1, 2, 0.5, 1.5, 1.1, 100, 1e6, 9)")
    db.execute("insert into prices values ('2026-11-19', 'TCS', 'NSE', 'EQ', 1, 2, 0.5, 1.4, 1.1, 100, 1e6, 9)")
    db.execute("insert into fx values ('2026-11-20', 'USDINR', 84.1)")
    db.execute("insert into corporate_actions (symbol, ex_date, kind, numerator, denominator, source) "
               "values ('TCS', '2026-03-01', 'split', 1, 5, 'nse')")
    db.execute("insert into fetch_log values ('nse_ca', '2026-03')")
    db.execute("insert into fund_costs values ('ppfas-flexi', '2026-11-01', 1.3, 0.6, 90000)")
    db.execute("insert into long_term_marks (symbol, marked_by) values ('TCS', 'father')")
    db.execute("insert into analyst_asks (symbol, asked_by, asked_on) values ('SBIN', 'father', '2026-11-24')")
    db.execute("insert into house_rule_edits (text, feedback_id, status) values ('Say sell, never exit.', 1, 'approved')")


def rows(db, table):
    return db.execute(f"select * from {table} order by all").fetchall()


@pytest.fixture
def seeded(tmp_path):
    db = store.open(tmp_path / "a.duckdb")
    seed(db)
    return db


def test_every_table_is_in_exactly_one_list(tmp_path):
    db = store.open(tmp_path / "x.duckdb")
    actual = {r[0] for r in db.execute("select table_name from information_schema.tables "
                                       "where table_schema = 'main'").fetchall()} - {"schema_migrations"}
    listed = set(backup.STATE_TABLES) | set(backup.MARKET_TABLES)
    assert not set(backup.STATE_TABLES) & set(backup.MARKET_TABLES)
    assert actual == listed, f"table in store.MIGRATIONS but in neither backup list: {actual ^ listed}"


def test_state_round_trip_gives_equal_rows(seeded, tmp_path):
    out = tmp_path / "private" / "state"
    backup.export_state(seeded, out)
    assert {p.name for p in out.iterdir()} == {f"{t}.parquet" for t in backup.STATE_TABLES}
    fresh = store.open(tmp_path / "b.duckdb")
    backup.load_state(fresh, out)
    for table in backup.STATE_TABLES:
        assert rows(fresh, table) == rows(seeded, table), table
        assert rows(seeded, table), f"seed has no rows for {table}"


def test_an_older_state_backup_loads_without_the_tables_added_since(seeded, tmp_path):
    out = tmp_path / "s"
    backup.export_state(seeded, out)
    for table in backup.ADDED_LATER:                       # a backup written before these tables existed
        (out / f"{table}.parquet").unlink()
    fresh = store.open(tmp_path / "b.duckdb")
    counts = backup.load_state(fresh, out)
    assert all(t not in counts for t in backup.ADDED_LATER)
    assert rows(fresh, "trades") == rows(seeded, "trades")


def test_a_missing_core_table_still_refuses_the_load(seeded, tmp_path):
    out = tmp_path / "s"
    backup.export_state(seeded, out)
    (out / "trades.parquet").unlink()
    with pytest.raises(backup.BackupError, match="trades"):
        backup.load_state(store.open(tmp_path / "b.duckdb"), out)


def test_state_load_keeps_ids_moving_forward(seeded, tmp_path):
    backup.export_state(seeded, tmp_path / "s")
    fresh = store.open(tmp_path / "b.duckdb")
    backup.load_state(fresh, tmp_path / "s")
    new_id = fresh.execute("insert into lots (kind, symbol, quantity) values ('stock', 'INFY', 1) returning id").fetchone()[0]
    assert new_id > seeded.execute("select max(id) from lots").fetchone()[0]


def test_load_state_refuses_a_store_that_has_state(seeded, tmp_path):
    backup.export_state(seeded, tmp_path / "s")
    with pytest.raises(backup.BackupError):
        backup.load_state(seeded, tmp_path / "s")


class Remote:
    """Stands in for the GitHub release: keeps what was uploaded."""
    def __init__(self):
        self.files = {}

    def upload(self, tag, paths):
        self.files = {p.name: p.read_bytes() for p in paths}
        self.tag = tag

    def download(self, tag, dest):
        assert tag == self.tag
        for name, data in self.files.items():
            (Path(dest) / name).write_bytes(data)


def test_market_round_trip_through_encryption(seeded, keys, tmp_path):
    remote = Remote()
    backup.backup_market(seeded, keys.recipient, remote.upload, work_dir=tmp_path / "w1")
    assert remote.tag == "market-backup"
    encrypted = [d for n, d in remote.files.items() if n.endswith(".age")]
    assert len(encrypted) == len(backup.MARKET_TABLES)
    for data in encrypted:
        assert b"PAR1" not in data
        assert data.startswith(b"age-encryption.org")
    fresh = store.open(tmp_path / "b.duckdb")
    backup.restore_market(fresh, keys.sealed_identity, PASSWORD, remote.download, work_dir=tmp_path / "w2")
    for table in backup.MARKET_TABLES:
        assert rows(fresh, table) == rows(seeded, table), table
    assert rows(fresh, "prices")


def test_a_market_backup_from_before_site_extras_went_still_restores(seeded, keys, tmp_path):
    remote = Remote()
    backup.backup_market(seeded, keys.recipient, remote.upload, work_dir=tmp_path / "w1")
    remote.files["site_extras.parquet.age"] = b"an old release still carries this file"
    fresh = store.open(tmp_path / "b.duckdb")
    counts = backup.restore_market(fresh, keys.sealed_identity, PASSWORD, remote.download, work_dir=tmp_path / "w2")
    assert "site_extras" not in counts and rows(fresh, "prices") == rows(seeded, "prices")
    assert not {"site_extras"} & {r[0] for r in fresh.execute("select table_name from information_schema.tables").fetchall()}


def test_market_restore_wrong_password(seeded, keys, tmp_path):
    remote = Remote()
    backup.backup_market(seeded, keys.recipient, remote.upload, work_dir=tmp_path / "w1")
    with pytest.raises(vault.VaultError):
        backup.restore_market(store.open(tmp_path / "b.duckdb"), keys.sealed_identity, "wrong",
                              remote.download, work_dir=tmp_path / "w2")


def test_work_files_are_removed_so_no_plaintext_parquet_stays_behind(seeded, keys, tmp_path):
    work = tmp_path / "w1"
    backup.backup_market(seeded, keys.recipient, Remote().upload, work_dir=work)
    assert not work.exists() or not list(work.iterdir())


def test_gh_uploader_makes_the_release_uploads_with_clobber_and_prunes_old_assets():
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        out = ""
        if argv[:3] == ["gh", "release", "view"]:
            out = json.dumps({"assets": [{"name": "prices.parquet.age"}, {"name": "gone.parquet.age"}]})
        return type("R", (), {"stdout": out, "returncode": 0})()
    backup.gh_upload("market-backup", [Path("/x/prices.parquet.age")], run=run)
    flat = [" ".join(c) for c in calls]
    assert any("release create market-backup" in c for c in flat) or any("release view market-backup" in c for c in flat)
    assert any("release upload market-backup /x/prices.parquet.age --clobber" in c for c in flat)
    assert any("release delete-asset market-backup gone.parquet.age" in c for c in flat)
    assert not any("delete-asset market-backup prices.parquet.age" in c for c in flat)


# --- the command line and the hooks -------------------------------------------------------------------------

import subprocess

from stockpilot import cli


@pytest.fixture
def root(tmp_path, keys):
    """A project root with vault keys and a bare git remote called origin."""
    r = tmp_path / "proj"
    (r / "config").mkdir(parents=True)
    keys.save(r / "config")
    bare = tmp_path / "remote.git"
    subprocess.run(["git", "init", "-q", "--bare", str(bare)], check=True)
    subprocess.run(["git", "init", "-q", str(r)], check=True)
    subprocess.run(["git", "remote", "add", "origin", str(bare)], cwd=r, check=True)
    (r / "config" / "stockpilot.yaml").write_text("vault:\n  remote: origin\n  paths: [private, .env]\n")
    return r


def _machine(cfg):
    """A Machine whose vault push is the real one over the project's git remote, counted."""
    from fakes import make_machine
    from stockpilot import machine as machine_mod
    real = machine_mod.real(cfg)
    m = make_machine(cfg.root)
    m.cfg = cfg
    m.pushes = 0

    def push():
        m.pushes += 1
        real.push_vault()
    m.push_vault = push
    return m


def test_state_survives_vault_push_restore_and_load_state(root, tmp_path):
    cfg = config.load(root)
    db = store.open(root / "data" / "stockpilot.duckdb")
    seed(db)
    m = _machine(cfg)
    assert ship.protect_state(m, db, "daily") == "pushed"
    assert db.execute("select count(*) from problems where message like 'state backup%'").fetchone()[0] == 0
    dest = tmp_path / "fresh"
    vault.restore(cli._remote_url(cfg), PASSWORD, dest)
    fresh = store.open(tmp_path / "fresh.duckdb")
    backup.load_state(fresh, dest / "private" / "state")
    for table in backup.STATE_TABLES:
        assert rows(fresh, table) == rows(db, table), table


def test_a_failed_state_backup_is_a_problem_not_a_crash(root):
    cfg = config.load(root)
    subprocess.run(["git", "remote", "set-url", "origin", "/nonexistent.git"], cwd=root, check=True)
    db = store.open(root / "data" / "stockpilot.duckdb")
    assert ship.protect_state(_machine(cfg), db, "queue").startswith("failed")
    assert db.execute("select count(*) from problems where job = 'queue' and message like 'state backup%'").fetchone()[0] == 1


def test_the_vault_is_pushed_only_when_an_owner_table_changed(root):
    cfg = config.load(root)
    db = store.open(root / "data" / "stockpilot.duckdb")
    seed(db)
    m = _machine(cfg)
    assert ship.protect_state(m, db, "daily") == "pushed"
    assert ship.protect_state(m, db, "daily") == "unchanged"
    journal.problem(db, "daily", "a log line")                 # logs do not count as a change
    db.execute("insert into runs (job, status) values ('daily_ingest', 'ok')")
    assert ship.protect_state(m, db, "daily") == "unchanged"
    db.execute("insert into budgets values ('2026-12', 1.0, 'owner', current_timestamp)")
    assert ship.protect_state(m, db, "daily") == "pushed"
    assert m.pushes == 2


def test_a_vault_push_runs_with_the_database_lock_free(root):
    cfg = config.load(root)
    m = _machine(cfg)
    seen = []
    m.push_vault = lambda: seen.append(store.holder(m.db_path))
    with m.db("daily") as db:
        seed(db)
        ship.protect_state(m, db, "daily")
    assert seen == [None]


def test_backup_command_writes_and_loads_state(root):
    db = store.open(root / "data" / "stockpilot.duckdb")
    seed(db)
    db.close()
    assert cli.main(["--root", str(root), "backup", "state"]) == 0
    assert (root / "private" / "state" / "lots.parquet").exists()
    (root / "data" / "stockpilot.duckdb").unlink()
    assert cli.main(["--root", str(root), "backup", "load-state"]) == 0
    assert store.open(root / "data" / "stockpilot.duckdb").execute("select count(*) from lots").fetchone()[0] == 1


def test_the_dossier_source_tables_are_in_the_market_backup():
    assert {"delivery", "deals", "results_calendar", "flows", "filings_index", "headlines"} <= set(backup.MARKET_TABLES)
