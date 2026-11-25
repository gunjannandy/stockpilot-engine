import json
from datetime import date
from pathlib import Path

from stockpilot import store
from stockpilot.sources import flows

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "dossier" / "nse_fii_dii.json").read_text())
DAY = date(2026, 11, 20)


def test_flows_store_one_row_per_category(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    paths = []

    def fetch_json(path):
        paths.append(path)
        return FIXTURE

    assert flows.ingest(db, DAY, fetch_json) == 2
    assert paths == ["/api/fiidiiTradeReact"]
    assert db.execute("select category, buy_cr, sell_cr, net_cr from flows order by category").fetchall() == [
        ("DII", 18492.63, 23352.43, -4859.8), ("FII", 23596.4, 13287.98, 10308.42)]


def test_flows_are_idempotent_and_history_builds_up_by_day(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    flows.ingest(db, DAY, lambda p: FIXTURE)
    flows.ingest(db, DAY, lambda p: FIXTURE)
    nxt = [{**r, "date": "23-Nov-2026"} for r in FIXTURE]
    flows.ingest(db, date(2026, 11, 23), lambda p: nxt)
    assert db.execute("select count(*) from flows").fetchone()[0] == 4
    assert db.execute("select count(distinct date) from flows").fetchone()[0] == 2
