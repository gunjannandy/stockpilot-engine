"""News headlines from Google News, fetched only for the stocks a dossier is being built for."""
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import duckdb

from stockpilot import journal
from stockpilot.sources import insert, transaction

RSS = "https://news.google.com/rss/search?q={q}&hl=en-IN&gl=IN&ceid=IN:en"
KEEP_DAYS = 30


def _items(blob: bytes) -> list[tuple]:
    out = []
    for item in ET.fromstring(blob).iter("item"):
        link, title, source = item.findtext("link"), item.findtext("title") or "", item.findtext("source") or ""
        if source and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        try:
            at = parsedate_to_datetime(item.findtext("pubDate")).astimezone(timezone.utc).replace(tzinfo=None)
        except (TypeError, ValueError):
            continue
        if link and title:
            out.append((at, title, source, link))
    return out


def for_symbols(db: duckdb.DuckDBPyConnection, day: date, symbols: list[str], names: dict[str, str], fetch) -> int:
    """Fetch headlines for `symbols` (company names from `names`); a symbol already fetched on `day` is skipped.
    Returns the new headlines stored."""
    before = db.execute("select count(*) from headlines").fetchone()[0]
    failed: dict[str, list[str]] = {}
    for symbol in symbols:
        key = f"headlines:{symbol}"
        if not names.get(symbol) or db.execute("select 1 from fetch_log where source = ? and period = ?",
                                               [key, day.isoformat()]).fetchone():
            continue
        try:
            items = _items(fetch(RSS.format(q=urllib.parse.quote(f'"{names[symbol]}" NSE'))))
        except Exception as err:   # one stock's feed failing must not stop the rest; it is retried next call
            failed.setdefault(f"{type(err).__name__}: {err}"[:160], []).append(symbol)
            continue
        with transaction(db):
            insert(db, "insert or ignore into headlines values (?, ?, ?, ?, ?, ?)",
                   [(symbol, at, title, source, link, day) for at, title, source, link in items])
            db.execute("insert or replace into fetch_log values (?, ?)", [key, day.isoformat()])
    _problems_by_cause(db, failed)
    stored = db.execute("select count(*) from headlines").fetchone()[0] - before
    db.execute("delete from headlines where published_at < ?",
               [datetime.combine(day - timedelta(days=KEEP_DAYS), datetime.min.time())])
    return stored


def _problems_by_cause(db, failed: dict[str, list[str]]) -> None:
    """One Health-tab row per cause, not per stock: 35 feeds failing for one reason is one line. The biggest cause keeps
    the key `headlines`; another cause gets its own, so two causes never overwrite each other."""
    for n, (cause, symbols) in enumerate(sorted(failed.items(), key=lambda kv: (-len(kv[1]), kv[0]))):
        stocks = f"{len(symbols)} stock" + ("" if len(symbols) == 1 else "s")
        journal.problem(db, "daily_decide", f"Google News failed for {stocks} ({cause}); for example {', '.join(symbols[:3])}.",
                        "warning", key="headlines" if n == 0 else f"headlines:{cause}"[:240])
