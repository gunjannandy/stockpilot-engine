from datetime import date
from pathlib import Path

from stockpilot import store

from stockpilot.sources import marketdata

FIXTURES = Path(__file__).parents[1] / "fixtures"


def fixture_fetch(url: str) -> bytes | None:
    """Serves saved real NSE files by name; anything else is a 404 (a holiday)."""
    path = FIXTURES / url.rsplit("/", 1)[-1]
    return path.read_bytes() if path.exists() else None


def test_ingests_equity_and_sme_rows_from_the_nse_bhavcopy(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    n = marketdata.ingest_nse_bhavcopy(db, date(2026, 11, 20), fixture_fetch)
    rows = dict(db.execute("select symbol, close from prices where date = '2026-11-20'").fetchall())
    assert n == 5
    assert rows["SBIN"] == 1165.10
    assert rows["MHHL"] == 25.30           # SME board stock the father watches
    assert "SGBJUN28" not in rows          # gold bonds are not stocks
    value = db.execute("select value from prices where symbol = 'SBIN'").fetchone()[0]
    assert value == 20313809384.30


def test_reingesting_a_day_does_not_duplicate(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    marketdata.ingest_nse_bhavcopy(db, date(2026, 11, 20), fixture_fetch)
    marketdata.ingest_nse_bhavcopy(db, date(2026, 11, 20), fixture_fetch)
    assert db.execute("select count(*) from prices").fetchone()[0] == 5


def test_a_day_without_a_file_ingests_nothing(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert marketdata.ingest_nse_bhavcopy(db, date(2026, 11, 22), fixture_fetch) == 0


def test_early_2024_files_with_a_trailing_comma_in_the_header(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert marketdata.ingest_nse_bhavcopy(db, date(2024, 1, 1), fixture_fetch) == 2


def test_ingests_the_legacy_bhavcopy_used_before_2024(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert marketdata.ingest_nse_bhavcopy(db, date(2023, 12, 29), fixture_fetch) == 3
    close, value = db.execute(
        "select close, value from prices where symbol = 'SBIN' and date = '2023-12-29'").fetchone()
    assert (close, value) == (642.05, 8494932618.15)


def test_bse_bhavcopy_brings_in_bse_only_stocks(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert marketdata.ingest_bse_bhavcopy(db, date(2026, 11, 20), fixture_fetch) == 6
    rows = dict(db.execute("select symbol, close from prices where exchange = 'BSE'").fetchall())
    assert rows["FORBESCO"] == 314.20
    assert rows["SOLARIUM"] == 96.48        # BSE SME (group M)


def test_index_closes_carry_valuation(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert marketdata.ingest_index_closes(db, date(2026, 11, 20), fixture_fetch) == 4
    row = db.execute("select close, pe, pb from index_levels where name = 'Nifty 50'").fetchone()
    assert row == (25800.6, 21.02, 3.17)


def test_bse_page_instead_of_the_file_says_bse_has_not_published_the_day(tmp_path):
    import pytest
    db = store.open(tmp_path / "sp.duckdb")
    page = b'<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>BSE India</title></head></html>'
    with pytest.raises(marketdata.NotPublished, match="BSE has not published 2026-11-23 yet"):
        marketdata.ingest_bse_bhavcopy(db, date(2026, 11, 23), lambda url: page)
    assert db.execute("select count(*) from prices").fetchone()[0] == 0




def test_a_session_on_a_day_the_calendar_calls_closed_is_found_and_stored(tmp_path):
    """Budget Sunday and Muhurat evening are real sessions on days the weekday rule and the holiday list call
    closed. The file's existence is the truth: look for it once per closed day and keep what is there."""
    db = store.open(tmp_path / "sp.duckdb")
    db.execute("insert into holidays values ('2026-11-20', 'pretend holiday')")
    asked = []

    def fetch(url):
        asked.append(url)
        return fixture_fetch(url)
    n = marketdata.ingest_special_sessions(db, date(2026, 11, 18), date(2026, 11, 22), fetch)
    assert n == 1                                                      # the pretend holiday had a file
    assert db.execute("select count(*) from prices where date = '2026-11-20' and exchange = 'NSE'").fetchone()[0] == 5
    closed_days = {"20261120", "20261121", "20261122"}                  # the holiday and the weekend, not Nov 18-19
    assert {u.split("_")[-3] for u in asked if "NSE_CM" in u} == closed_days


def test_a_closed_day_is_asked_about_only_once(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    asked = []
    marketdata.ingest_special_sessions(db, date(2026, 11, 21), date(2026, 11, 23), lambda u: asked.append(u))
    first = len(asked)
    marketdata.ingest_special_sessions(db, date(2026, 11, 21), date(2026, 11, 23), lambda u: asked.append(u))
    assert first > 0 and len(asked) == first


def test_a_day_with_prices_already_is_not_asked_about(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    marketdata.ingest_nse_bhavcopy(db, date(2026, 11, 20), fixture_fetch)
    db.execute("insert into holidays values ('2026-11-20', 'x')")
    asked = []
    marketdata.ingest_special_sessions(db, date(2026, 11, 20), date(2026, 11, 20), lambda u: asked.append(u))
    assert asked == []


def test_a_special_session_keeps_nse_only(tmp_path):
    """BSE history is not kept day by day; one lone BSE day would read as a jump against a months-old BSE row."""
    db = store.open(tmp_path / "sp.duckdb")
    db.execute("insert into holidays values ('2026-11-20', 'x')")
    marketdata.ingest_special_sessions(db, date(2026, 11, 20), date(2026, 11, 22), fixture_fetch)
    assert db.execute("select count(*) from prices where exchange = 'BSE'").fetchone()[0] == 0
