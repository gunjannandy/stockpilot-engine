"""R4 migration: the calls row grows the forecaster's fields, and not_now and archived_days exist."""
from datetime import date

from stockpilot import backup, store

NEW_CALL_COLUMNS = {"section", "expected_gain_inr", "hurdle", "change_reason", "summary_bn", "would_buy_if",
                    "level_flag", "warnings", "acted_on", "base_rate_n"}


def test_calls_gain_the_forecaster_columns(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    cols = {r[0] for r in db.execute("select column_name from information_schema.columns where table_name = 'calls'").fetchall()}
    assert NEW_CALL_COLUMNS <= cols


def test_not_now_has_the_owner_contract_and_its_ids_move_forward(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    cols = [r[0] for r in db.execute("select column_name from information_schema.columns where table_name = 'not_now' "
                                     "order by ordinal_position").fetchall()]
    assert cols == ["id", "symbol", "scope", "until", "set_by", "set_at", "undone_at", "how"]
    db.execute("insert into not_now (symbol, scope, until, set_by) values ('SBIN', 'buy', null, 'papa')")
    db.execute("insert into not_now (symbol, scope, until, set_by) values ('TCS', 'any', ?, 'me')", [date(2026, 12, 1)])
    assert [r[0] for r in db.execute("select id from not_now order by id").fetchall()] == [1, 2]
    assert backup.SEQUENCES["not_now"] == "not_now_id"


def test_the_new_tables_are_owner_state(tmp_path):
    assert {"not_now", "archived_days"} <= set(backup.STATE_TABLES)
