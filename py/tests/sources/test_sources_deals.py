import json
from datetime import date
from pathlib import Path

from stockpilot import store
from stockpilot.sources import deals

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "dossier" / "nse_bulk_block.json").read_text())
DAY = date(2026, 11, 20)


def test_deals_store_bulk_and_block_but_not_short_deals(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    paths = []

    def fetch_json(path):
        paths.append(path)
        return FIXTURE

    assert deals.ingest(db, DAY, fetch_json) == 10
    assert paths == ["/api/snapshot-capital-market-largedeal"]
    assert db.execute("select kind, count(*) from deals group by kind order by kind").fetchall() == [("block", 5), ("bulk", 5)]
    assert db.execute("select date, kind, client, side, quantity, price from deals where symbol = 'BLSPOLY' "
                      "and quantity = 414422").fetchone() == (
        DAY, "bulk", "ALPHAGREP SECURITIES PRIVATE LIMITED", "BUY", 414422, 273.3)
    assert db.execute("select price from deals where symbol = 'GALLANTT'").fetchone() == (523.0,)


def test_deals_are_idempotent_per_day(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    deals.ingest(db, DAY, lambda p: FIXTURE)
    deals.ingest(db, DAY, lambda p: FIXTURE)
    assert db.execute("select count(*) from deals").fetchone()[0] == 10


def test_an_empty_answer_stores_nothing(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert deals.ingest(db, DAY, lambda p: {}) == 0
