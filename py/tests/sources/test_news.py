import json
from datetime import date
from pathlib import Path

from stockpilot import store

from stockpilot.sources import news

FIXTURES = Path(__file__).parents[1] / "fixtures"


def test_announcements_are_stored_per_symbol_with_their_text(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    items = json.loads((FIXTURES / "nse_announcements.json").read_text())
    assert news.ingest_announcements(db, date(2026, 11, 20), lambda path: items) == 3
    rows = db.execute("select subject, text from announcements where symbol = 'SHALPAINTS' order by announced_at desc").fetchall()
    assert [r[0] for r in rows][:1] == ["Allotment of Securities"]
    assert "Qualified Institution Placement" in rows[0][1]


def test_headlines_come_back_newest_first_with_source(tmp_path):
    xml = (FIXTURES / "google_news_sbin.xml").read_bytes()
    heads = news.headlines("State Bank of India", fetch=lambda url: xml, limit=2)
    assert len(heads) == 2
    assert heads[0]["published"] >= heads[1]["published"]
    assert heads[0]["source"] == "Simply Wall St"
    assert not heads[0]["title"].endswith("- Simply Wall St")
