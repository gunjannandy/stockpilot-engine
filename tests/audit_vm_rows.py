"""AUDIT: rows the VM would write to D1, made by the REAL Python code (feedback_read.rows, wire.changes_for), so the browser check in
web/tests/e2e-audit.mjs shows what production would show. Usage: uv run python tests/audit_vm_rows.py <out.json>"""
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from test_feedback_read import MESSAGES, recorded_model  # noqa: E402

from stockpilot import feedback_read as fr  # noqa: E402
from stockpilot.jobs import wire  # noqa: E402


FIXN = Path(__file__).parent / "fixtures" / "news"
INGEST_KEY = "audit-ingest-worker-key-0123456789ab"


def news_rows() -> dict:
    """The REAL collector over fixture feeds, its signed POSTs recorded (the browser check replays them through the real ingest Worker),
    then the REAL VM tag and rank handlers over the same rows (the tagged rows, the news_rank rows, the In today's news list and its changes)."""
    import re
    from stockpilot.sources import news_collect as nc
    from jobs.test_wire import NOW, Rig, Scripted  # noqa: E402 - tests/ is on the path
    universe = json.loads((FIXN / "universe.json").read_text())["entries"]
    read = lambda n: (FIXN / n).read_text()  # noqa: E731

    def fetch(url):
        if "bseindia" in url:
            return read("bse_announcements.json").encode()
        if "nseindia" in url:
            return read("nse_announcements.json").encode()
        if "news.google.com" in url:
            return read("google_alpha.xml").encode()
        return read("publisher_et.xml").encode()
    posts = []

    def post(url, body, headers):
        posts.append({"body": body, "headers": headers})
        return {"written": len(json.loads(body)["rows"]), "writes_today": 1, "stopped": False}
    now = datetime.fromisoformat("2026-11-25T10:00:00+05:30")
    nc.collect(universe, {}, now=now, fetch=fetch, post=post, url="https://ingest.invalid/", key=INGEST_KEY, log=lambda *_: None)
    rig = Rig()
    for p in posts:
        b = json.loads(p["body"])
        for r in b["rows"]:
            cols = list(r)
            rig.db.execute(f"insert or replace into {b['table']} ({','.join(cols)}) values ({','.join('?' * len(cols))})", [int(v) if isinstance(v, bool) else v for v in r.values()])
    rig.db.execute("insert into lists values ('holdings','FIXA','NSE',1,'held','','2026-11-01T00:00:00+05:30')")
    rig.db.execute("insert into lists values ('watchlist','FIXB','NSE',1,'watched','','2026-11-01T00:00:00+05:30')")
    rig.db.commit()

    def tag(prompt):
        ids = re.findall(r"id:(\S+?)\|", prompt)
        tagged = []
        for i in ids:
            row = rig.db.execute("select title from news_items where id = ?", [i]).fetchone()
            sym = [(t["symbol"], t["exchange"]) for t in rig.db.execute("select symbol, exchange from news_tags where item_id = ?", [i])]
            tagged.append({"id": i, "sector": "Fixture sector", "direction": "good", "impact": 4, "line_en": f"{row['title']}: good for the company.",
                           "line_bn": "কোম্পানির জন্য ভালো খবর।", "touches": [{"symbol": s, "exchange": x, "relation": "self", "direction": "good",
                                                                            "size": "medium", "changes_call": True} for s, x in sym]})
        return json.dumps(tagged)
    rig.models["gemini-a"] = Scripted("gemini-a", {"Tag each news item": tag})
    rig.state.clear()
    rig.fire(now=NOW)
    rig.fire()                                        # the tag job runs
    rig.fire()                                        # the rank job runs, writing the list
    dump = lambda sql: [dict(r) for r in rig.db.execute(sql)]  # noqa: E731
    return {"posts": posts, "key": INGEST_KEY, "news_items": dump("select * from news_items"), "news_tags": dump("select * from news_tags"),
            "news_rank": dump("select * from news_rank"), "lists": dump("select * from lists where list_name = 'in_the_news'"),
            "list_changes": dump("select * from changes where kind like 'list_%'")}


def main(out: str) -> None:
    msg = MESSAGES["10"]                                   # data, bug, data: two asks wait for the owner, one is built on a schedule
    asks = fr.rows("fb_audit", fr.read(msg["text"], "father", recorded_model(), ["fake"]), "2026-11-26T09:00:00+05:30")
    rec = {"call": "buy", "chance_3m": 0.64, "summary": "Order win lifts the chance.", "summary_bn": "অর্ডার জয়ে সম্ভাবনা বেড়েছে।"}
    before = {"call": "hold", "chance_3m": 0.52}
    marks = wire.changes_for({"id": "job_audit", "asked_by": "father"}, "FIXA", before, rec, "2026-11-26T09:10:00+05:30")
    Path(out).write_text(json.dumps({"feedback": {"id": "fb_audit", "person": "father", "text": msg["text"], "status": "understood",
                                                   "created_at": "2026-11-26T09:00:00+05:30"}, "asks": asks, "changes": marks, "news": news_rows()},
                                    ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main(sys.argv[1])
