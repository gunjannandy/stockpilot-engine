"""News for the brief, fetched by code so any runner can reason over it: NSE company announcements
(official filings) and Google News RSS headlines (personal, non-commercial use per the feed's terms)."""
import json
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime
from email.utils import parsedate_to_datetime

import duckdb

RSS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"


def ingest_announcements(db: duckdb.DuckDBPyConnection, day: date, fetch_json) -> int:
    stamp = day.strftime("%d-%m-%Y")
    items = fetch_json(f"/api/corporate-announcements?index=equities&from_date={stamp}&to_date={stamp}") or []
    rows = [(datetime.strptime(i["an_dt"], "%d-%b-%Y %H:%M:%S"), i["symbol"], i.get("desc"),
             i.get("attchmntText"), i.get("attchmntFile")) for i in items if i.get("symbol")]
    db.executemany("insert or replace into announcements values (?, ?, ?, ?, ?)", rows)
    return len(rows)


def headlines(query: str, fetch, limit: int = 5) -> list[dict]:
    root = ET.fromstring(fetch(RSS.format(q=urllib.parse.quote(f'"{query}"'))))
    out = []
    for item in root.iter("item"):
        source = item.findtext("source") or ""
        title = item.findtext("title") or ""
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        out.append({"title": title, "source": source, "link": item.findtext("link"),
                    "published": parsedate_to_datetime(item.findtext("pubDate")).isoformat()})
    out.sort(key=lambda h: h["published"], reverse=True)
    return out[:limit]
