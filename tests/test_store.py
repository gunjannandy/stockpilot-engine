from stockpilot import store


def test_new_store_holds_the_core_tables(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    tables = {r[0] for r in db.execute("select table_name from information_schema.tables").fetchall()}
    assert {"prices", "fundamentals", "holdings", "lots", "watchlist", "calls", "runs", "requests"} <= tables


def test_reopening_keeps_data_and_version(tmp_path):
    path = tmp_path / "sp.duckdb"
    db = store.open(path)
    db.execute("insert into watchlist (symbol, exchange, added_by) values ('SBIN', 'NSE', 'import')")
    version = store.version(db)
    db.close()
    db = store.open(path)
    assert store.version(db) == version
    assert db.execute("select count(*) from watchlist").fetchone()[0] == 1


def test_site_extras_is_dropped_and_what_the_dashboard_still_needs_is_carried_over(tmp_path):
    """The migration that drops site_extras keeps the last feedback summary and the fund calls (now a weekly report)."""
    import json
    path = tmp_path / "old.duckdb"
    db = store.open(path)
    drop = next(i for i, m in enumerate(store.MIGRATIONS, 1) if "drop table site_extras" in m)
    assert drop < len(store.MIGRATIONS)                       # later lanes append migrations; old ones are never edited
    db.close()
    import duckdb
    raw = duckdb.connect(str(path))
    raw.execute("create table site_extras (name varchar primary key, built_on date, body json)")
    raw.execute("insert into site_extras values ('feedback_changes', '2026-11-20', ?), ('fund_calls', '2026-11-21', ?), ('tokens', '2026-11-20', '[]')",
                [json.dumps(["Planned: bigger fonts"]), json.dumps({"as_of": "2026-11-21", "calls": [{"name": "F"}]})])
    raw.execute("drop table feedback_changes")
    raw.execute("delete from schema_migrations where version >= ?", [drop])
    for later in ("gaps", "long_term_marks", "analyst_asks", "ownership", "house_rule_edits", "price_flags", "demerger_factors", "fidelity_holdings", "fidelity_lots"):   # tables of the migrations after `drop`
        raw.execute(f"drop table {later}")
    raw.execute("alter table lots drop column estimated")      # P1: the migration that adds it runs again
    raw.execute("drop sequence analyst_ask_id")
    raw.execute("drop sequence house_rule_id")
    raw.close()
    db = store.open(path)
    tables = {r[0] for r in db.execute("select table_name from information_schema.tables").fetchall()}
    assert "site_extras" not in tables
    assert json.loads(db.execute("select changes from feedback_changes").fetchone()[0]) == ["Planned: bigger fonts"]
    week, body = db.execute("select week_of, payload from weekly_reports where section = 'fund_calls'").fetchone()
    assert str(week) == "2026-11-21" and json.loads(body)["calls"] == [{"name": "F"}]
