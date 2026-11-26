"""AUDIT #19: the writers for the `holdings`, `watchlist` and `worth_following` lists of the live contract (the `in_the_news` list has
its own, `news_lists.py`). Pure rules here; `jobs/wire.py` reads the sources and writes D1.

- The first fill of a list writes its rows and no yellow marks (otherwise every holding would light up once).
- After that, a stock that enters or leaves a list is one yellow change for each person, with a stable id, so a repeated run writes nothing.
- A stock that was a candidate and is now held enters Holdings; it does not also "leave" Worth following (Worth following never holds held stocks).
- Worth following is the best candidates by the nightly numbers, ten to enter and up to fifteen kept, so a stock near the line does not flap."""
from stockpilot.news_lists import PEOPLE

ENTER, STAY, CAP = 10, 20, 15      # best 10 may join; a member stays while in the best 20; at most 15 shown
NAMES = {"holdings": ("Holdings", "হোল্ডিং"), "watchlist": ("Watchlist", "নজরে রাখা তালিকা"),
         "worth_following": ("Worth following", "দেখার মতো")}
COMPARE = ("rank", "reason", "reason_bn", "since")


def _key(r):
    return r["symbol"], r["exchange"]


def _change(job_id, person, symbol, kind, name, old, new, reason, reason_bn, at) -> dict:
    return {"id": f"chg_{job_id}_{person}_{symbol}_{kind}_{name}", "person": person, "symbol": symbol, "kind": kind, "old_value": old,
            "new_value": new, "reason": reason, "reason_bn": reason_bn, "at": at, "seen_at": None}


def diff(name: str, desired: list[dict], old: list[dict], job_id: str, at: str, moved=frozenset()):
    """(rows to write, keys to delete, changes). `desired` rows carry symbol, exchange, reason, reason_bn, best first.
    Only a row that is new or different is returned: D1 counts every write. `moved` are symbols that left because they went to another list."""
    was = {_key(o): o for o in old}
    now = {_key(d) for d in desired}
    rows = []
    for rank, d in enumerate(desired, 1):
        row = {"list_name": name, "symbol": d["symbol"], "exchange": d["exchange"], "rank": rank, "reason": d["reason"],
               "reason_bn": d.get("reason_bn"), "since": (was.get(_key(d)) or {}).get("since") or at}
        o = was.get(_key(d))
        if not o or any(o[k] != row[k] for k in COMPARE):
            rows.append(row)
    drop = [k for k in was if k not in now]
    marks = []
    if old:                                                       # not the first fill
        en, bn = NAMES[name]
        for d in desired:
            if _key(d) not in was:
                marks += [_change(job_id, p, d["symbol"], "list_entered", name, None, name, d["reason"], d.get("reason_bn"), at) for p in PEOPLE]
        for sym, ex in drop:
            if sym not in moved:
                marks += [_change(job_id, p, sym, "list_left", name, name, None, f"No longer on {en}.", f"আর {bn}-এ নেই।", at) for p in PEOPLE]
    return rows, drop, marks


def worth_following(cands: list[dict], held: set[str], old_symbols: set[str]) -> list[dict]:
    """Desired rows for Worth following from `{symbol, exchange, chance_3m, chance_6m}` candidates."""
    scored = sorted(((c, (c["chance_3m"] + c["chance_6m"]) / 2) for c in cands if c["symbol"] not in held),
                    key=lambda cs: (-cs[1], cs[0]["symbol"]))
    keep = [cs for cs in scored[:STAY] if cs[0]["symbol"] in old_symbols]
    join = [cs for cs in scored[:ENTER] if cs[0]["symbol"] not in old_symbols]
    best = sorted(keep + join, key=lambda cs: (-cs[1], cs[0]["symbol"]))[:CAP]
    out = []
    for c, _ in best:
        pct = round(c["chance_6m"] * 100)
        out.append({"symbol": c["symbol"], "exchange": c["exchange"],
                    "reason": f"Our numbers give a {pct}% chance of beating the Nifty in 6 months.",
                    "reason_bn": f"আমাদের হিসাবে ৬ মাসে Nifty-কে ছাড়িয়ে যাওয়ার সম্ভাবনা {pct}%।"})
    return out
