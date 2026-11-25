import json
from datetime import date, datetime
from pathlib import Path

from stockpilot import store
from stockpilot.sources import filings

FIXTURE = json.loads((Path(__file__).parents[1] / "fixtures" / "dossier" / "nse_financial_results.json").read_text())
DAY = date(2026, 11, 20)
PATH = "/api/corporates-financial-results?index=equities&period=Quarterly"


def test_filings_index_stores_the_filing_list(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    paths = []

    def fetch_json(path):
        paths.append(path)
        return FIXTURE

    assert filings.ingest(db, DAY, fetch_json) == 5
    assert paths == [PATH]
    row = db.execute("select isin, period_from, period_to, consolidated, audited, filed_at, xbrl_url "
                     "from filings_index where symbol = 'VSTTILLERS' and consolidated").fetchone()
    assert row == ("INE764D01017", date(2024, 10, 1), date(2024, 12, 31), True, False,
                   datetime(2026, 7, 30, 17, 17), FIXTURE[0]["xbrl"])
    assert db.execute("select count(*) from filings_index where symbol = 'VSTTILLERS' and not consolidated"
                      ).fetchone()[0] == 1


def test_a_dash_instead_of_a_link_is_stored_as_no_link(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    filings.ingest(db, DAY, lambda p: FIXTURE)
    assert db.execute("select xbrl_url from filings_index where symbol = 'ARSHIYA'").fetchone() == (None,)


def test_filings_are_idempotent(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    filings.ingest(db, DAY, lambda p: FIXTURE)
    assert filings.ingest(db, DAY, lambda p: FIXTURE) == 5
    assert db.execute("select count(*) from filings_index").fetchone()[0] == 5
