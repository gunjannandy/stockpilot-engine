"""The "In today's news" list (spec #24 stories 34 and 50): the stocks that today's news made interesting, updated whenever news is
ranked. Pure rules here; `jobs/wire.py` reads and writes D1. A stock that enters or leaves the list is a yellow change for both people."""
from datetime import datetime, timedelta

LIST = "in_the_news"
MAX_STOCKS = 12
MIN_IMPACT = 3                    # impact runs 1 to 5; below 3 is not "in the news"
FRESH = timedelta(hours=36)       # today's news, with a night either side
PEOPLE = ("owner", "father")


def pick(items: list[dict], touches: dict[str, list[dict]], now: datetime) -> list[dict]:
    """Stocks named by recent, important items. Best first: impact, then how many sources agree, then newest. A stock the news is
    about (relation "self") comes before a rival or supplier that is only touched. One row per stock."""
    keep = [i for i in items if (i.get("impact") or 0) >= MIN_IMPACT and now - datetime.fromisoformat(i["published_at"]) <= FRESH]
    keep.sort(key=lambda i: i["published_at"], reverse=True)                                     # newest first ...
    keep.sort(key=lambda i: (-(i["impact"] or 0), -(i.get("source_count") or 1)))                # ... then the stable sort puts impact and sources first
    out, seen = [], set()
    for tier in ("self", "other"):
        for it in keep:
            for t in touches.get(it["id"], []):
                key = (t["symbol"], t["exchange"])
                if key in seen or (t.get("relation") == "self") != (tier == "self"):
                    continue
                seen.add(key)
                out.append({"symbol": t["symbol"], "exchange": t["exchange"], "reason": it.get("line_en") or it.get("title") or "In the news",
                            "reason_bn": it.get("line_bn")})
    return out[:MAX_STOCKS]


def rows(picked: list[dict], old: list[dict], stamp: str) -> list[dict]:
    """The `lists` rows for the new list. A stock already on the list keeps its `since`."""
    since = {(o["symbol"], o["exchange"]): o["since"] for o in old}
    return [{"list_name": LIST, "symbol": p["symbol"], "exchange": p["exchange"], "rank": n, "reason": p["reason"], "reason_bn": p["reason_bn"],
             "since": since.get((p["symbol"], p["exchange"]), stamp)} for n, p in enumerate(picked, 1)]


def changes(new: list[dict], old: list[dict], job_id: str, at: str) -> list[dict]:
    """Entered and left, for each person. The id is stable, so a repeated run cannot write a change twice."""
    was, now = {(o["symbol"], o["exchange"]): o for o in old}, {(n["symbol"], n["exchange"]): n for n in new}
    out = []
    for key, n in now.items():
        if key not in was:
            out += [_change(job_id, p, key[0], "list_entered", None, LIST, n["reason"], n["reason_bn"], at) for p in PEOPLE]
    for key, o in was.items():
        if key not in now:
            out += [_change(job_id, p, key[0], "list_left", LIST, None, "No longer in today's news.", "আর আজকের খবরে নেই।", at) for p in PEOPLE]
    return out


def _change(job_id, person, symbol, kind, old, new, reason, reason_bn, at) -> dict:
    return {"id": f"chg_{job_id}_{person}_{symbol}_{kind}", "person": person, "symbol": symbol, "kind": kind, "old_value": old,
            "new_value": new, "reason": reason, "reason_bn": reason_bn, "at": at, "seen_at": None}
