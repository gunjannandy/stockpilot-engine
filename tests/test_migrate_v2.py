"""Lane V3: the v1 -> v2 migration, on synthetic rows with neutral ids. No network, no real data."""
import json
import sqlite3
from pathlib import Path

import pytest

from stockpilot import jobrun, migrate_v2, store

MIGRATION_SQL = Path(__file__).resolve().parents[1] / "web" / "migrations" / "0001_live_contract.sql"


def seed(db):
    for sym in ("ACME", "BOLT", "CRUX"):
        db.execute("insert into trades (trade_key, source, kind, symbol, side, trade_date, quantity, price) "
                   "values (?, 'tradebook', 'stock', ?, 'buy', '2026-01-02', 5, 100.5)", [f"k-{sym}", sym])
        db.execute("insert into lots (kind, symbol, acquired_on, quantity, cost_per_unit) "
                   "values ('stock', ?, '2026-01-02', 5, 100.5)", [sym])
    db.execute("insert into watchlist (symbol, exchange, added_by, added_at) values ('ACME', 'NSE', 'papa', '2026-02-01 10:00:00')")
    db.execute("insert into watchlist (symbol, exchange, added_by, added_at) values ('DELT', 'BSE', 'owner', '2026-02-02 10:00:00')")
    db.execute("insert into watchlist (symbol, exchange, added_by, added_at, removed_at) "
               "values ('GONE', 'NSE', 'owner', '2026-02-03 10:00:00', '2026-03-01 10:00:00')")
    db.execute("insert into runs (job, status) values ('daily', 'ok')")
    for day in ("2026-11-20", "2026-11-21"):
        db.execute("insert into calls (run_id, made_on, symbol, kind, action, reasons) values (1, ?, 'ACME', 'stock', 'hold', '[\"fair\"]')", [day])
        db.execute("insert into archived_days (day) values (?)", [day])
    db.execute("insert into long_term_marks (symbol, marked_by) values ('ACME', 'father')")
    db.execute("insert into long_term_marks (symbol, marked_by) values ('BOLT', 'owner')")
    db.execute("insert into feedback (\"at\", author, kind, text, status, backlog_id) values ('2026-11-20 09:00:00', 'papa', 'want', 'Bigger fonts', 'auto', 41)")
    db.execute("insert into feedback (\"at\", author, kind, text, status) values ('2026-11-21 09:00:00', 'owner', 'bug', 'Chart is blank', 'new')")
    db.execute("insert into fund_calls (made_on, isin, scheme_code, name, category, call, code_call, line, detail) values "
               "('2026-11-21', 'INF1', 1, 'Fund 1', 'Flexi Cap', 'Keep', 'Keep', 'Nothing to do.', '{}')")
    db.execute("insert into fidelity_lots values ('2025-12-31', 'RSUCO', 'US0000000001', '2025-11-17', 20, 300000, 15000, 277000, -23000, "
               "'2025-11-17', '2023-03-15', 'short')")
    db.execute("insert into fidelity_lots values ('2025-12-31', 'RSUCO', 'US0000000001', '2025-08-17', 10, 150000, 15000, 138000, -12000, "
               "'2025-08-17', '2023-03-15', 'long')")
    db.execute("insert into fidelity_events values ('f1', 'vest', '2025-02-14', 'G1', 7, 5, 790.25, 3951.25, null, null)")
    db.execute("insert into fidelity_holdings values ('2026-11-24', 'RSUCO', 'US0000000001', 339, 4479761.57, 2874999.61, 91.28)")


@pytest.fixture
def v1(tmp_path):
    db = store.open(tmp_path / "v1.duckdb")
    seed(db)
    return db


def test_every_record_type_is_counted_and_matches(v1, tmp_path):
    report = migrate_v2.migrate(v1, tmp_path / "v2")
    assert set(report["types"]) == {"trades", "lots", "watchlist", "call_archive", "marks", "feedback", "fund_calls", "rsu_lots"}
    expected = {"trades": 3, "lots": 3, "watchlist": 3, "call_archive": 2 + 2, "marks": 2, "feedback": 2, "fund_calls": 1, "rsu_lots": 2 + 1 + 1}
    assert {k: v["v1"] for k, v in report["types"].items()} == expected
    assert all(v["v1"] == v["v2"] and v["v1_sha"] == v["v2_sha"] for v in report["types"].values())
    assert report["ok"] is True


def test_verify_reads_the_files_again_and_catches_a_dropped_row(v1, tmp_path):
    out = tmp_path / "v2"
    migrate_v2.migrate(v1, out)
    assert migrate_v2.verify(v1, out)["ok"] is True
    v1.execute("insert into long_term_marks (symbol, marked_by) values ('NEWY', 'owner')")      # v1 moved on after the copy
    with pytest.raises(migrate_v2.MigrationError, match="marks"):
        migrate_v2.verify(v1, out)


def test_a_damaged_destination_file_is_caught(v1, tmp_path):
    out = tmp_path / "v2"
    migrate_v2.migrate(v1, out)
    (out / "trades" / "trades.parquet").write_bytes(b"not parquet")
    with pytest.raises(migrate_v2.MigrationError, match="trades"):
        migrate_v2.verify(v1, out)


def test_migrating_twice_gives_the_same_proof(v1, tmp_path):
    a = migrate_v2.migrate(v1, tmp_path / "a")
    b = migrate_v2.migrate(v1, tmp_path / "b")
    assert a["types"] == b["types"]


def test_d1_rows_follow_the_live_contract(v1, tmp_path):
    migrate_v2.migrate(v1, tmp_path / "v2")
    for table in ("feedback", "lists"):
        rows = json.loads((tmp_path / "v2" / "d1" / f"{table}.json").read_text())
        assert rows
        shape = jobrun.CONTRACT["tables"][table]["columns"]
        for row in rows:
            assert jobrun.check_shape(row, shape) == [], (table, row)


def test_feedback_people_are_neutral_and_old_ones_read_as_understood(v1, tmp_path):
    migrate_v2.migrate(v1, tmp_path / "v2")
    rows = {r["text"]: r for r in json.loads((tmp_path / "v2" / "d1" / "feedback.json").read_text())}
    assert rows["Bigger fonts"]["person"] == "father" and rows["Chart is blank"]["person"] == "owner"
    assert rows["Bigger fonts"]["status"] == "understood" and rows["Chart is blank"]["status"] == "received"
    assert rows["Bigger fonts"]["created_at"] == "2026-11-20T09:00:00+05:30"


def test_only_stocks_still_on_the_watchlist_reach_the_d1_list(v1, tmp_path):
    migrate_v2.migrate(v1, tmp_path / "v2")
    rows = json.loads((tmp_path / "v2" / "d1" / "lists.json").read_text())
    assert sorted(r["symbol"] for r in rows) == ["ACME", "DELT"]
    assert {r["list_name"] for r in rows} == {"watchlist"}
    assert [r["rank"] for r in rows] == [1, 2]
    # the removed stock is not lost: the private copy keeps all 3 watchlist rows
    assert migrate_v2.migrate(v1, tmp_path / "again")["types"]["watchlist"]["v2"] == 3


def test_seed_sql_loads_into_d1s_real_schema_with_matching_counts(v1, tmp_path):
    migrate_v2.migrate(v1, tmp_path / "v2")
    d1 = sqlite3.connect(":memory:")
    d1.executescript(MIGRATION_SQL.read_text())
    d1.executescript((tmp_path / "v2" / "d1" / "seed.sql").read_text())
    d1.executescript((tmp_path / "v2" / "d1" / "seed.sql").read_text())          # safe to run twice
    assert d1.execute("select count(*) from feedback").fetchone()[0] == 2
    assert d1.execute("select count(*) from lists where list_name = 'watchlist'").fetchone()[0] == 2


def test_a_quote_in_feedback_text_survives_the_seed_sql(v1, tmp_path):
    v1.execute("insert into feedback (\"at\", author, kind, text) values ('2026-11-22 09:00:00', 'papa', 'want', 'Don''t hide the ''why''; drop table feedback;--')")
    migrate_v2.migrate(v1, tmp_path / "v2")
    d1 = sqlite3.connect(":memory:")
    d1.executescript(MIGRATION_SQL.read_text())
    d1.executescript((tmp_path / "v2" / "d1" / "seed.sql").read_text())
    assert d1.execute("select count(*) from feedback where text = ?", ["Don't hide the 'why'; drop table feedback;--"]).fetchone()[0] == 1


def test_the_report_holds_counts_and_hashes_but_no_row_content(v1, tmp_path):
    migrate_v2.migrate(v1, tmp_path / "v2")
    text = (tmp_path / "v2" / "manifest.json").read_text()
    assert "Bigger fonts" not in text and "ACME" not in text
    assert json.loads(text)["types"]["trades"]["v1"] == 3
