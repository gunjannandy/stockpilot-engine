from datetime import date
from pathlib import Path

from stockpilot import store
from stockpilot.sources import delivery

FIXTURE = Path(__file__).parents[1] / "fixtures" / "dossier" / "sec_bhavdata_full_20112026.csv"
DAY = date(2026, 11, 20)


def test_delivery_parses_the_bhavcopy_with_delivery_percent(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    urls = []

    def fetch(url):
        urls.append(url)
        return FIXTURE.read_bytes()

    n = delivery.ingest(db, DAY, fetch)
    assert urls == ["https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_20112026.csv"]
    assert n == db.execute("select count(*) from delivery").fetchone()[0] > 0
    assert db.execute("select deliv_qty, deliv_pct from delivery where symbol = '20MICRONS' and series = 'EQ'"
                      ).fetchone() == (17830, 51.75)


def test_delivery_keeps_only_eq_and_be_and_treats_a_dash_as_unknown(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    delivery.ingest(db, DAY, lambda url: FIXTURE.read_bytes())
    assert {s for (s,) in db.execute("select distinct series from delivery").fetchall()} <= {"EQ", "BE"}
    assert db.execute("select deliv_qty, deliv_pct from delivery where symbol = '21STCENMGM'").fetchone() == (None, None)


def test_delivery_is_idempotent_and_a_missing_file_stores_nothing(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    first = delivery.ingest(db, DAY, lambda url: FIXTURE.read_bytes())
    assert delivery.ingest(db, DAY, lambda url: FIXTURE.read_bytes()) == first
    assert db.execute("select count(*) from delivery").fetchone()[0] == first
    assert delivery.ingest(db, date(2026, 11, 21), lambda url: None) == 0
