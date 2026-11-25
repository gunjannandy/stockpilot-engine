from datetime import date, datetime
from pathlib import Path

from stockpilot import store
from stockpilot.sources import headlines

XML = (Path(__file__).parents[1] / "fixtures" / "dossier" / "google_news_tatasteel.xml").read_bytes()
DAY = date(2026, 11, 23)
NAMES = {"TATASTEEL": "Tata Steel", "SBIN": "State Bank of India"}


def test_headlines_fetch_by_company_name_and_store_title_source_and_time(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    urls = []

    def fetch(url):
        urls.append(url)
        return XML

    assert headlines.for_symbols(db, DAY, ["TATASTEEL"], NAMES, fetch) == 3
    assert urls == ["https://news.google.com/rss/search?q=%22Tata%20Steel%22%20NSE&hl=en-IN&gl=IN&ceid=IN:en"]
    row = db.execute("select published_at, title, source, fetched_on from headlines "
                     "where source = 'Moneycontrol.com'").fetchone()
    assert row[0] == datetime(2026, 11, 22, 15, 42, 38)
    assert row[1].startswith("Tata Steel inches closer") and not row[1].endswith("Moneycontrol.com")
    assert row[3] == DAY


def test_a_symbol_already_fetched_that_day_is_skipped_but_not_the_next_day(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    calls = []
    fetch = lambda url: calls.append(url) or XML
    headlines.for_symbols(db, DAY, ["TATASTEEL"], NAMES, fetch)
    assert headlines.for_symbols(db, DAY, ["TATASTEEL"], NAMES, fetch) == 0
    assert len(calls) == 1
    headlines.for_symbols(db, date(2026, 11, 24), ["TATASTEEL"], NAMES, fetch)
    assert len(calls) == 2
    assert db.execute("select count(*) from headlines").fetchone()[0] == 3      # same links, not stored twice


def test_a_symbol_with_no_headlines_is_still_marked_fetched(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    empty = b'<?xml version="1.0"?><rss version="2.0"><channel><title>x</title></channel></rss>'
    calls = []
    fetch = lambda url: calls.append(url) or empty
    assert headlines.for_symbols(db, DAY, ["SBIN"], NAMES, fetch) == 0
    headlines.for_symbols(db, DAY, ["SBIN"], NAMES, fetch)
    assert len(calls) == 1


def test_only_30_days_are_kept(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    headlines.for_symbols(db, DAY, ["TATASTEEL"], NAMES, lambda url: XML)
    later = date(2026, 12, 25)      # the 20 Nov item is 35 days old, the 22 Nov one 33
    headlines.for_symbols(db, later, ["SBIN"], NAMES,
                          lambda url: b'<rss version="2.0"><channel></channel></rss>')
    assert db.execute("select count(*) from headlines").fetchone()[0] == 0


def test_one_failing_symbol_does_not_stop_the_others_and_is_retried_later(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")

    def fetch(url):
        if "Tata" in url:
            raise ConnectionError("Google down")
        return XML

    assert headlines.for_symbols(db, DAY, ["TATASTEEL", "SBIN"], NAMES, fetch) == 3
    assert {s for (s,) in db.execute("select distinct symbol from headlines").fetchall()} == {"SBIN"}
    assert db.execute("select count(*) from problems").fetchone()[0] == 1
    assert headlines.for_symbols(db, DAY, ["TATASTEEL"], NAMES, lambda url: XML) == 3


def test_a_symbol_without_a_known_name_is_left_out(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert headlines.for_symbols(db, DAY, ["NONAME"], NAMES, lambda url: XML) == 0
