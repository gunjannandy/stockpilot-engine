"""AUDIT #19 and #23: the "In today's news" list is written by the VM when it ranks news, and a stock that enters or leaves it
reaches both people as a yellow change. Before this nothing wrote the list, so it never changed and no list change ever existed."""
from datetime import datetime, timedelta, timezone

from stockpilot import news_lists
from test_wire import NOW, Rig

IST = timezone(timedelta(hours=5, minutes=30))


def seed(rig, item_id, symbol, impact, published="2026-11-25T08:00:00+05:30", relation="self", exchange="NSE", sources=1):
    rig.db.execute("insert into news_items (id,link,title,source,published_at,group_id,source_count,market_wide,direction,impact,line_en,line_bn,tagged_at)"
                   " values (?,?,?,?,?,?,?,?,?,?,?,?,?)", (item_id, "https://x/" + item_id, f"{symbol} story", "Wire", published, item_id, sources, 0, "good",
                                                           impact, f"{symbol}: order win.", f"{symbol}: অর্ডার জয়।", "2026-11-25T08:30:00+05:30"))
    rig.db.execute("insert into news_tags values (?,?,?,?,?,?,?)", (item_id, symbol, exchange, relation, "good", "medium", 0))
    rig.db.commit()


def lists(rig):
    return [(r["symbol"], r["rank"]) for r in rig.db.execute("select * from lists where list_name = 'in_the_news' order by rank")]


def changes(rig):
    return sorted((r["person"], r["symbol"], r["kind"], r["old_value"], r["new_value"]) for r in rig.db.execute("select * from changes where kind like 'list_%'"))


def test_pick_takes_important_recent_stocks_best_first_and_skips_the_weak_and_the_old():
    items = [{"id": "a", "published_at": "2026-11-25T08:00:00+05:30", "impact": 5, "source_count": 3, "line_en": "A news.", "line_bn": "ক", "title": "A"},
             {"id": "b", "published_at": "2026-11-25T09:00:00+05:30", "impact": 3, "source_count": 1, "line_en": "B news.", "line_bn": "খ", "title": "B"},
             {"id": "c", "published_at": "2026-11-25T09:00:00+05:30", "impact": 2, "source_count": 9, "line_en": "C news.", "line_bn": "গ", "title": "C"},
             {"id": "d", "published_at": "2026-11-20T09:00:00+05:30", "impact": 5, "source_count": 9, "line_en": "D news.", "line_bn": "ঘ", "title": "D"}]
    touches = {i: [{"symbol": s, "exchange": "NSE", "relation": "self"}] for i, s in zip("abcd", ["AAA", "BBB", "CCC", "DDD"])}
    got = news_lists.pick(items, touches, NOW)
    assert [g["symbol"] for g in got] == ["AAA", "BBB"]                                   # impact 2 is too small, a five-day-old item is not today's news
    assert got[0]["reason"] == "A news." and got[0]["reason_bn"] == "ক"


def test_ranking_writes_the_list_and_a_stock_entering_it_is_a_yellow_change_for_both_people():
    rig = Rig()
    seed(rig, "n1", "FIXA", 4)
    seed(rig, "n2", "FIXB", 3, exchange="BSE")
    rig.add("news_rank", {}, by="system")
    rig.fire()
    assert lists(rig) == [("FIXA", 1), ("FIXB", 2)]
    assert changes(rig) == [("father", "FIXA", "list_entered", None, "in_the_news"), ("father", "FIXB", "list_entered", None, "in_the_news"),
                            ("owner", "FIXA", "list_entered", None, "in_the_news"), ("owner", "FIXB", "list_entered", None, "in_the_news")]
    row = rig.db.execute("select * from lists where symbol = 'FIXB'").fetchone()
    assert row["exchange"] == "BSE" and row["reason"] == "FIXB: order win." and row["reason_bn"] and row["since"]


def test_a_second_run_with_the_same_news_changes_nothing_and_keeps_since():
    rig = Rig()
    seed(rig, "n1", "FIXA", 4)
    rig.add("news_rank", {}, by="system"); rig.fire()
    since = rig.db.execute("select since from lists where symbol = 'FIXA'").fetchone()["since"]
    before = changes(rig)
    rig.fire(now=NOW + timedelta(hours=1)); rig.add("news_rank", {}, by="system"); rig.fire()
    assert changes(rig) == before and rig.db.execute("select since from lists where symbol = 'FIXA'").fetchone()["since"] == since


def test_a_stock_whose_news_goes_stale_leaves_the_list_with_a_yellow_change():
    rig = Rig()
    seed(rig, "n1", "FIXA", 4)
    rig.add("news_rank", {}, by="system"); rig.fire()
    rig.fire(now=NOW + timedelta(days=3))                                                # the story is now three days old
    rig.add("news_rank", {}, by="system"); rig.fire()
    assert lists(rig) == []
    assert ("father", "FIXA", "list_left", "in_the_news", None) in changes(rig) and ("owner", "FIXA", "list_left", "in_the_news", None) in changes(rig)
