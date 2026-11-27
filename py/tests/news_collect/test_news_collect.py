"""Public news collector (ticket T11): grouping, ticker matching, links-only rows, write-only door, privacy."""
import hashlib
import hmac
import json
import re
from datetime import datetime
from pathlib import Path

from stockpilot.sources import news_collect as nc

FIX = Path(__file__).parent.parent / "fixtures" / "news"
CONTRACT = json.loads((Path(__file__).parents[3] / "schemas" / "live-contract.json").read_text())
UNIVERSE = json.loads((FIX / "universe.json").read_text())["entries"]
NOW = datetime.fromisoformat("2026-11-25T10:00:00+05:30")


def read(name):
    return (FIX / name).read_text()


def all_items():
    return (nc.parse_rss(read("publisher_et.xml"), "Example ET")
            + nc.parse_google_rss(read("google_alpha.xml"))
            + nc.parse_nse(json.loads(read("nse_announcements.json")))
            + nc.parse_bse(json.loads(read("bse_announcements.json"))))


def test_every_source_parses_to_links_only_items():
    items = all_items()
    assert {i["source"] for i in items} >= {"Example ET", "Example Mint", "Example Wire", "NSE", "BSE"}
    for i in items:
        assert set(i) == {"link", "title", "source", "published_at"}
        assert i["link"].startswith("http") and i["published_at"].endswith("+05:30")
    mint = [i for i in items if i["source"] == "Example Mint"][0]
    assert mint["title"] == "Fixture Alpha Q2 profit jumps 40% on strong demand"   # " - Publisher" removed


def test_one_event_from_three_sources_is_one_item_with_source_count_3():
    groups = nc.group_items(all_items())
    alpha = [g for g in groups if "alpha" in g["title"].lower() and "q2" in g["title"].lower()]
    assert len(alpha) == 1
    assert alpha[0]["source_count"] == 4          # ET, Mint, NSE, BSE report it
    three = nc.group_items([i for i in all_items() if i["source"] in ("Example ET", "Example Mint", "NSE")
                            and "q2" in i["title"].lower()])
    assert len(three) == 1 and three[0]["source_count"] == 3
    assert three[0]["source"] == "NSE"             # the exchange filing is the primary source


def test_different_events_stay_apart_and_same_source_twice_counts_once():
    groups = nc.group_items(all_items())
    titles = " | ".join(g["title"] for g in groups)
    assert "RBI keeps repo rate" in titles and "export deal" in titles
    dup = nc.group_items([{"link": "https://example.invalid/a", "title": "Same story today", "source": "X", "published_at": "2026-11-25T09:00:00+05:30"},
                          {"link": "https://example.invalid/b", "title": "Same story today", "source": "X", "published_at": "2026-11-25T09:05:00+05:30"}])
    assert len(dup) == 1 and dup[0]["source_count"] == 1


def test_names_match_tickers_from_the_public_universe_only():
    syms = {t["symbol"] for t in nc.match_tickers("Fixture Alpha Ltd Q2 profit jumps 40%", UNIVERSE)}
    assert syms == {"FIXA"}
    assert nc.match_tickers("RBI keeps repo rate unchanged", UNIVERSE) == []
    assert {t["symbol"] for t in nc.match_tickers("Fixture Beta and Fixture Delta sign pact", UNIVERSE)} == {"FIXB", "FIXD"}


def test_rows_fit_the_contract_and_hold_no_article_text():
    rows = nc.build_rows(nc.group_items(all_items()), UNIVERSE)
    for table in ("news_items", "news_tags"):
        cols = CONTRACT["tables"][table]["columns"]
        required = {c for c, t in cols.items() if not t.endswith("?")}
        assert rows[table]
        for r in rows[table]:
            assert set(r) <= set(cols) and required <= set(r), (table, r)
    item = next(r for r in rows["news_items"] if "export deal" in r["title"])
    assert item["direction"] == "none" and item["impact"] == 0 and item["tagged_at"] is None
    assert item["market_wide"] is False
    assert next(r for r in rows["news_items"] if "RBI" in r["title"])["market_wide"] is True
    assert {(t["item_id"], t["symbol"]) for t in rows["news_tags"]} >= {(item["id"], "FIXB")}


def test_second_run_writes_only_what_is_new(tmp_path):
    state = {}
    first = nc.new_rows(nc.build_rows(nc.group_items(all_items()), UNIVERSE), state, NOW)
    again = nc.new_rows(nc.build_rows(nc.group_items(all_items()), UNIVERSE), state, NOW)
    assert first["news_items"] and not again["news_items"] and not again["news_tags"]


def test_rows_go_through_the_ingest_worker_signed_like_the_worker_checks():
    sent = []

    def post(url, body, headers):
        sent.append((url, body, headers))
        return {"written": len(json.loads(body)["rows"]), "writes_today": 5, "stopped": False}

    rows = [{"n": i} for i in range(450)]
    nc.write_table("news_items", rows, url="https://ingest.example.invalid/api/v2/ingest", key="k" * 20, post=post, now_ms=1_700_000_000_000)
    assert [len(json.loads(b)["rows"]) for _, b, _ in sent] == [200, 200, 50]
    for url, body, h in sent:
        assert url == "https://ingest.example.invalid/api/v2/ingest"
        want = hmac.new(b"k" * 20, f"1700000000000.{body}".encode(), hashlib.sha256).hexdigest()
        assert h["X-SP-Signature"] == want and h["X-SP-Timestamp"] == "1700000000000"


def test_a_stopped_budget_ends_the_run_without_losing_state():
    calls = []

    def post(url, body, headers):
        calls.append(1)
        return {"written": 0, "writes_today": 85000, "stopped": True}

    out = nc.write_table("news_items", [{"n": 1}] * 300, url="u", key="k" * 20, post=post, now_ms=1)
    assert out["stopped"] and len(calls) == 1 and out["written"] == 0


def test_no_private_names_reach_queries_or_logs():
    """The public job takes no holdings or watchlist input; its Google queries are market topics plus a time-rotated
    slice of the whole universe, so they are the same whatever the owner holds."""
    a = nc.google_queries(UNIVERSE, NOW, per_run=2)
    b = nc.google_queries(UNIVERSE, NOW, per_run=2)
    assert a == b
    assert set(nc.MARKET_TOPICS) <= set(a)
    assert nc.google_queries(UNIVERSE, datetime.fromisoformat("2026-11-25T10:15:00+05:30"), per_run=2) != a
    import inspect
    sig = inspect.signature(nc.collect)
    assert not any(w in p for p in sig.parameters for w in ("hold", "watch", "portfolio"))
    src = inspect.getsource(nc)
    assert not re.search(r"^\s*(from|import)\s+stockpilot\.(store|watchlist|vault|sources\.kite|book|trades)", src, re.M)


def test_collect_logs_only_counts(capsys):
    fetched = {}

    def fetch(url):
        fetched[url] = 1
        if "bseindia" in url:
            return read("bse_announcements.json").encode()
        if "nseindia" in url:
            return read("nse_announcements.json").encode()
        if "news.google.com" in url:
            return read("google_alpha.xml").encode()
        return read("publisher_et.xml").encode()

    posted = []
    log = []
    nc.collect(UNIVERSE, {}, now=NOW, fetch=fetch, post=lambda u, b, h: posted.append(json.loads(b)) or {"written": len(json.loads(b)["rows"]), "writes_today": 1, "stopped": False},
               url="https://ingest.example.invalid/api/v2/ingest", key="k" * 20, log=log.append)
    text = " ".join(log)
    assert not re.search(r"FIX[A-D]|Fixture", text)
    assert re.search(r"\d+ new", text)
    assert {p["table"] for p in posted} == {"news_items", "news_tags"}


def test_news_older_than_90_days_moves_to_monthly_files():
    state = {"items": {
        "old1": {"id": "old1", "title": "Old", "published_at": "2026-08-01T10:00:00+05:30", "source_count": 1},
        "old2": {"id": "old2", "title": "Old too", "published_at": "2026-08-20T10:00:00+05:30", "source_count": 2},
        "new1": {"id": "new1", "title": "New", "published_at": "2026-11-20T10:00:00+05:30", "source_count": 1}}}
    files = nc.archive_old(state, NOW)
    assert sorted(files) == ["news/2026-08.json"]
    assert [r["id"] for r in files["news/2026-08.json"]] == ["old1", "old2"]
    assert list(state["items"]) == ["new1"]
