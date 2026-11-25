"""Public news collector (ticket T11), run every 15 minutes by a public job.

Whole market only: NSE and BSE announcements, Google News for market topics and a time-rotated slice of the public
universe, and six publisher feeds. It takes no holdings or watchlist input, so nothing private can reach a request or
a log. Reports of one event are grouped and counted by source. Rows hold links only (link, title, time, source) and go
through the ingest Worker, signed with its key, never straight to D1. News older than 90 days moves to monthly files."""
import hashlib
import hmac
import json
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

IST = timezone(timedelta(hours=5, minutes=30))
GOOGLE = "https://news.google.com/rss/search?q={q}+when:1d&hl=en-IN&gl=IN&ceid=IN:en"
NSE_PATH = "https://www.nseindia.in/api/corporate-announcements?index=equities"
BSE_URL = "https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w?pageno=1&strCat=-1&subcategory=-1&strPrevDate={d}&strToDate={d}&strSearch=P&strscrip=&strType=C"
BSE_FILE = "https://www.bseindia.com/xml-data/corpfiling/AttachLive/{f}"
PUBLISHER_FEEDS = {
    "Economic Times": "https://economictimes.indiatimes.com/markets/rssfeeds/1977021501.cms",
    "Mint": "https://www.livemint.com/rss/markets",
    "Business Standard": "https://www.business-standard.com/rss/markets-106.rss",
    "BusinessLine": "https://www.thehindubusinessline.com/markets/feeder/default.rss",
    "Moneycontrol": "https://www.moneycontrol.com/rss/marketreports.xml",
    "NDTV Profit": "https://www.ndtvprofit.com/rss/markets",
}
MARKET_TOPICS = ["Sensex Nifty", "RBI monetary policy", "FII DII flows India", "IPO India", "India quarterly results",
                 "SEBI order", "crude oil rupee", "India budget GST", "bank stocks India", "IT stocks India",
                 "auto sales India", "pharma stocks India"]
EXCHANGES = ("NSE", "BSE")
ARCHIVE_DAYS = 90
MAX_ROWS = 200                         # the Worker's per-call limit
SAME_EVENT = 0.6                       # share of title words two reports must have in common
SAME_EVENT_WINDOW = timedelta(hours=48)
STOP_WORDS = {"the", "a", "an", "of", "in", "on", "to", "for", "and", "at", "by", "with", "as", "is", "its", "ltd", "limited"}


def _ist(dt: datetime) -> str:
    dt = dt.replace(tzinfo=IST) if dt.tzinfo is None else dt.astimezone(IST)
    return dt.isoformat(timespec="seconds")


def _item(link, title, source, when):
    title = re.sub(r"\s+", " ", title or "").strip()
    return {"link": link, "title": title, "source": source, "published_at": _ist(when)} if link and title else None


def parse_rss(xml: str, source: str) -> list[dict]:
    out = []
    for e in ET.fromstring(xml).iter("item"):
        when = parsedate_to_datetime(e.findtext("pubDate")) if e.findtext("pubDate") else None
        it = when and _item(e.findtext("link"), e.findtext("title"), source, when)
        if it:
            out.append(it)
    return out


def parse_google_rss(xml: str) -> list[dict]:
    out = []
    for e in ET.fromstring(xml).iter("item"):
        source, title = e.findtext("source") or "Google News", e.findtext("title") or ""
        if source != "Google News" and title.endswith(f" - {source}"):
            title = title[: -len(source) - 3]
        if e.findtext("pubDate"):
            it = _item(e.findtext("link"), title, source, parsedate_to_datetime(e.findtext("pubDate")))
            if it:
                out.append(it)
    return out


def parse_nse(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows or []:
        text = (r.get("attchmntText") or "").strip() or f"{r.get('symbol', '')} {r.get('desc') or 'announcement'}"
        it = _item(r.get("attchmntFile"), text, "NSE", datetime.strptime(r["an_dt"], "%d-%b-%Y %H:%M:%S"))
        if it:
            out.append(it)
    return out


def parse_bse(doc: dict) -> list[dict]:
    out = []
    for r in (doc or {}).get("Table") or []:
        name, head = (r.get("SLONGNAME") or "").strip(), (r.get("HEADLINE") or "").strip()
        title = head if name.lower() in head.lower() else f"{name}: {head}"
        link = BSE_FILE.format(f=r["ATTACHMENTNAME"]) if r.get("ATTACHMENTNAME") else None
        it = _item(link, title, "BSE", datetime.fromisoformat(r["NEWS_DT"]))
        if it:
            out.append(it)
    return out


def _words(title: str) -> frozenset:
    return frozenset(w for w in re.findall(r"[a-z0-9]+", title.lower()) if w not in STOP_WORDS)


def _when(it) -> datetime:
    return datetime.fromisoformat(it["published_at"])


def group_items(items: list[dict]) -> list[dict]:
    """One group per event. A group is stable: its id comes from its earliest report, so a later report joins it
    instead of making a new one. source_count counts distinct sources."""
    groups = []
    for it in sorted(items, key=_when):
        w = _words(it["title"])
        for g in groups:
            if abs(_when(it) - _when(g["items"][0])) <= SAME_EVENT_WINDOW and \
                    len(w & g["words"]) / max(1, len(w | g["words"])) >= SAME_EVENT:
                g["items"].append(it)
                break
        else:
            groups.append({"items": [it], "words": w})
    out = []
    for g in groups:
        first = g["items"][0]
        lead = next((i for i in g["items"] if i["source"] in EXCHANGES), first)
        out.append({"group_id": hashlib.sha1(" ".join(sorted(_words(first["title"]))).encode()).hexdigest()[:16],
                    "link": lead["link"], "title": lead["title"], "source": lead["source"],
                    "published_at": first["published_at"], "source_count": len({i["source"] for i in g["items"]})})
    return out


def _norm(name: str) -> str:
    return " ".join(w for w in re.findall(r"[a-z0-9&]+", name.lower()) if w not in ("ltd", "limited"))


def match_tickers(title: str, universe: list[dict]) -> list[dict]:
    """Stocks the headline names: company name or alias as a whole phrase, or the symbol as a capitalised word.
    Looks only at the public universe."""
    text, words, found = f" {_norm(title)} ", set(re.findall(r"\b[A-Z0-9&]{3,}\b", title)), []
    for e in universe:
        names = {_norm(e["name"]), *(_norm(a) for a in e.get("aliases", []))}
        if any(len(n) >= 5 and f" {n} " in text for n in names) or e["symbol"] in words:
            found.append({"symbol": e["symbol"], "exchange": e["exchange"]})
    return found


def build_rows(groups: list[dict], universe: list[dict]) -> dict:
    """news_items rows are untagged (direction none, impact 0): the tagger fills them later. news_tags rows are only
    the stocks a headline names, marked small and mixed until the tagger overwrites them."""
    items, tags = [], []
    for g in groups:
        hits = match_tickers(g["title"], universe)
        items.append({"id": g["group_id"], "link": g["link"], "title": g["title"], "source": g["source"],
                      "published_at": g["published_at"], "group_id": g["group_id"], "source_count": g["source_count"],
                      "sector": None, "market_wide": not hits, "direction": "none", "impact": 0,
                      "line_en": None, "line_bn": None, "tagged_at": None})
        tags += [{"item_id": g["group_id"], **h, "relation": "self", "direction": "mixed", "size": "small",
                  "changes_call": False} for h in hits]
    return {"news_items": items, "news_tags": tags}


def new_rows(rows: dict, state: dict, now: datetime) -> dict:
    """Only events not seen before. The Worker replaces a row it already holds, which would wipe the tagger's work, so
    an event is written once; a later source for it raises the count only in the next tagging pass."""
    seen = state.setdefault("items", {})
    fresh = {r["id"] for r in rows["news_items"] if r["id"] not in seen}
    for r in rows["news_items"]:
        if r["id"] in fresh:
            seen[r["id"]] = {"id": r["id"], "title": r["title"], "link": r["link"], "source": r["source"],
                             "published_at": r["published_at"], "source_count": r["source_count"],
                             "first_seen": _ist(now)}
    return {"news_items": [r for r in rows["news_items"] if r["id"] in fresh],
            "news_tags": [r for r in rows["news_tags"] if r["item_id"] in fresh]}


def archive_old(state: dict, now: datetime) -> dict:
    """Pull items older than 90 days out of the state into monthly files ({'news/2026-08.json': [rows]})."""
    cutoff, files = now - timedelta(days=ARCHIVE_DAYS), {}
    for key, r in sorted(state.get("items", {}).items(), key=lambda kv: kv[1]["published_at"]):
        if _when(r) < cutoff:
            files.setdefault(f"news/{r['published_at'][:7]}.json", []).append(r)
    for rows in files.values():
        for r in rows:
            del state["items"][r["id"]]
    return files


def google_queries(universe: list[dict], now: datetime, per_run: int = 25) -> list[str]:
    """Market topics every run, plus a slice of the whole universe that moves on every 15 minutes, so every stock is
    searched in turn whatever anyone holds."""
    names = [e["name"] for e in universe]
    slot = int(now.timestamp() // 900)
    start = (slot * per_run) % max(1, len(names))
    pick = (names + names)[start:start + per_run] if names else []
    return MARKET_TOPICS + [f'"{_norm(n)}" stock' for n in pick]


def _sign(key: str, ts: str, body: str) -> str:
    return hmac.new(key.encode(), f"{ts}.{body}".encode(), hashlib.sha256).hexdigest()


def http_post(url, body, headers):
    req = urllib.request.Request(url, data=body.encode(), headers={"Content-Type": "application/json", **headers})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read())


def write_table(table, rows, *, url, key, post=http_post, now_ms=None) -> dict:
    """Send rows to the ingest Worker in calls of at most 200, each signed. Stops when the Worker says it is stopped."""
    import time
    out = {"written": 0, "writes_today": None, "stopped": False}
    for i in range(0, len(rows), MAX_ROWS):
        body = json.dumps({"table": table, "rows": rows[i:i + MAX_ROWS]}, separators=(",", ":"))
        ts = str(now_ms if now_ms is not None else int(time.time() * 1000))
        try:
            res = post(url, body, {"X-SP-Timestamp": ts, "X-SP-Signature": _sign(key, ts, body)})
        except urllib.error.HTTPError as err:
            if err.code != 429:
                raise
            res = {"written": 0, "writes_today": None, "stopped": True}
        out["written"] += res["written"]
        out["writes_today"] = res["writes_today"]
        if res["stopped"]:
            out["stopped"] = True
            break
    return out


def collect(universe, state, *, now, fetch, post=http_post, url, key, log=print, per_run=25) -> dict:
    """One run. Every line logged is a count: no symbol, name or headline ever reaches a log."""
    items, failed = [], 0

    def get(what, url_, parse):
        nonlocal failed
        try:
            blob = fetch(url_)
            items.extend(parse(blob.decode() if isinstance(blob, bytes) else blob))
        except Exception:                  # one dead feed must not stop the others
            failed += 1

    get("nse", NSE_PATH, lambda t: parse_nse(json.loads(t)))
    get("bse", BSE_URL.format(d=now.strftime("%Y%m%d")), lambda t: parse_bse(json.loads(t)))
    for name, feed in PUBLISHER_FEEDS.items():
        get(name, feed, lambda t, n=name: parse_rss(t, n))
    for q in google_queries(universe, now, per_run):
        get("google", GOOGLE.format(q=urllib.parse.quote(q)), parse_google_rss)
    rows = new_rows(build_rows(group_items(items), universe), state, now)
    sent = {}
    for table in ("news_items", "news_tags"):
        if rows[table]:
            sent[table] = write_table(table, rows[table], url=url, key=key, post=post)
    log(f"news_collect: {len(items)} reports read, {len(rows['news_items'])} new events, {len(rows['news_tags'])} stock tags, "
        f"{failed} feeds failed, stopped={any(s['stopped'] for s in sent.values())}")
    return {"new": len(rows["news_items"]), "failed": failed, "sent": sent}


def main(argv):
    """python -m stockpilot.sources.news_collect <search_index.json> <state.json> <archive_dir>
    Needs SP_INGEST_URL and SP_INGEST_KEY in the environment."""
    import gzip, os
    from pathlib import Path
    from stockpilot.sources import http
    universe = json.loads(Path(argv[0]).read_text())["entries"]
    state_path, out_dir = Path(argv[1]), Path(argv[2])
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    now = datetime.now(IST)

    def fetch(u):
        if "nseindia" in u:
            from stockpilot.sources.nse_api import Session
            return json.dumps(fetch.nse.fetch_json(u.split("nseindia.in", 1)[1])).encode()
        return http.fetch(u)
    from stockpilot.sources.nse_api import Session
    fetch.nse = Session()
    collect(universe, state, now=now, fetch=fetch, url=os.environ["SP_INGEST_URL"], key=os.environ["SP_INGEST_KEY"])
    for name, rows in archive_old(state, now).items():
        path = out_dir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        old = json.loads(path.read_text()) if path.exists() else []
        path.write_text(json.dumps(old + rows, ensure_ascii=False))
    state_path.write_text(json.dumps(state, ensure_ascii=False))


if __name__ == "__main__":
    import sys
    main(sys.argv[1:])
