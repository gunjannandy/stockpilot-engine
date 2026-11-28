"""The news Job, every 15 minutes: collect public news, rank by source weight, judge each new item once per stock, and
publish. Public data only: no holdings or watchlist ever reaches it.

Items are published as the `news_items` dataset (ranked); impact rows go to the Worker's append-only door
`/api/news/impact`, where every consumer reads them. `news_rank.spread()` is gone: a sector tag never makes a row."""
from datetime import datetime

from stockpilot.runtime import JobContext
from stockpilot.sources import news_collect as nc

from .impact import judge, unjudged
from .weights import rank_items

KIND = "news"
ITEMS = "news_items"
MAX_JUDGED_PER_RUN = 60
# One run publishes at most this many ranked items: 96 runs a day at this size stay inside the dataset's day write budget.
MAX_PUBLISHED = 50


def item_row(i: dict) -> dict:
    return {"id": i["group_id"], "link": i["link"], "title": i["title"], "source": i["source"],
            "published_at": i["published_at"], "source_count": i["source_count"], "weight": i["weight"]}


def run(ctx: JobContext, *, fetch=None, model=None, article=None, universe=None, now: datetime | None = None) -> str:
    now = now or datetime.now(nc.IST)
    fetch = fetch or _live_fetch()
    if universe is None:
        rows = ctx.client._ok("/api/stocks/universe", None, "GET").get("rows", [])
        universe = [{"symbol": r["symbol"], "exchange": r["exchange"], "name": r["name"], "aliases": r.get("aliases", [])}
                    for r in rows if r["status"] == "listed"]
    reports = []
    for name, url, parse in sources(now, universe):
        try:
            blob = fetch(url)
            if blob is None:  # the server has no such file (404): nothing from this feed, not a failure
                ctx.progress.line(f"feed {name} has nothing right now")
                continue
            reports += parse(blob.decode() if isinstance(blob, bytes) else blob)
        except Exception:  # noqa: BLE001 - one dead feed must not stop the others
            ctx.progress.line(f"feed {name} failed", "fail")
    items = rank_items([{**g, "id": g["group_id"]} for g in nc.group_items(reports)], now)
    ctx.publish(ITEMS, [item_row(i) for i in items[:MAX_PUBLISHED]], source="nse, bse, publisher feeds", as_of=str(ctx.range.end))
    judged = 0
    if model is not None:
        have = set(ctx.client._ok("/api/news/judged", None, "GET").get("item_ids", []))
        fresh = unjudged(items, have)[:MAX_JUDGED_PER_RUN]
        out, answered = judge(fresh, model, nc._ist(now), article)
        if answered:
            ctx.client._ok("/api/news/impact", {"rows": out, "judged_ids": answered})
        judged = len(fresh)
    return f"{len(items)} news items ranked, {judged} judged"


def sources(now, universe):
    import json
    import urllib.parse
    yield "nse", nc.NSE_PATH, lambda t: nc.parse_nse(json.loads(t))
    yield "bse", nc.BSE_URL.format(d=now.strftime("%Y%m%d")), lambda t: nc.parse_bse(json.loads(t))
    for name, feed in nc.PUBLISHER_FEEDS.items():
        yield name, feed, lambda t, n=name: nc.parse_rss(t, n)
    for q in nc.google_queries(universe, now):
        yield "google", nc.GOOGLE.format(q=urllib.parse.quote(q)), nc.parse_google_rss


def _live_fetch():
    import json

    from stockpilot.sources import http
    from stockpilot.sources.nse_api import Session
    nse = Session()

    def fetch(u):
        if "nseindia" in u:
            return json.dumps(nse.fetch_json(u.split("nseindia.in", 1)[1])).encode()
        return http.fetch(u)
    return fetch
