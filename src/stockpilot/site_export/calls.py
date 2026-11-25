"""What is new about the calls: the kind of sell, what changed since last time, and what is unusual today."""
import json
from datetime import date, datetime, time, timedelta

from stockpilot.site_export import plain

ACTIONABLE = ("buy", "add", "sell", "trim")
MOVED_BY = 0.05          # a chance that moved this much since the last run
VOLUME_TIMES = 2.0
AT_TREND = 0.01
SOON_DAYS = 14
ACTION_WORDS = ("dividend", "split", "bonus", "rights", "buyback")


def sell_kind(section, kind=None):
    """"sell", "weak" or "review" for a sell or trim call, None for every other call. The forecaster sets the kind on the
    call (lane E): sell = its sell price was reached, the analyst says the reason for owning it broke, or the size limit;
    weak = a low chance alone; review = a holding he keeps for years. A call stored before the field existed is "sell" if
    it is a trim and "weak" otherwise: the cautious reading."""
    if section not in ("sell", "trim"):
        return None
    if kind in ("sell", "weak", "review"):
        return kind
    return "sell" if section == "trim" else "weak"


def annotate(cards, key):
    """Set `sell_kind` on every card (None unless it is a sell or trim), from the field the forecaster stored on the call."""
    for c in cards:
        c["sell_kind"] = sell_kind(c.get(key), c.get("sell_kind"))


def previous_calls(db, day: date):
    """(date, {symbol: (action, probability)}) of the run before the newest one, or (None, {})."""
    made = db.execute("select max(made_on) from calls where made_on <= ?", [day]).fetchone()[0]
    prev = db.execute("select max(made_on) from calls where made_on < ?", [made]).fetchone()[0] if made else None
    if not prev:
        return None, {}
    rows = db.execute("select symbol, action, probability from calls where made_on = ? "
                      "qualify row_number() over (partition by symbol order by id desc) = 1", [prev]).fetchall()
    return prev, {s: (a, p) for s, a, p in rows}


def since(db, day: date, cards) -> dict:
    """The strip on Today: new, changed, dropped and moved calls against the run before."""
    prev_on, prev = previous_calls(db, day)
    cur = {c["symbol"]: c for c in cards}
    live = {s: c for s, c in cur.items() if c["action"] in ACTIONABLE}
    new = sorted(s for s in live if s not in prev)
    changed = [{"symbol": s, "from": prev[s][0], "to": c["action"]} for s, c in sorted(live.items())
               if s in prev and prev[s][0] != c["action"]]
    dropped = sorted(s for s, (a, _) in prev.items() if a in ACTIONABLE and s not in live)
    shown = {x["symbol"] for x in changed}
    moved = [{"symbol": s, "from": round(prev[s][1], 3), "to": round(c["probability"], 3)} for s, c in sorted(live.items())
             if s in prev and s not in shown and prev[s][1] is not None and c["probability"] is not None
             and abs(c["probability"] - prev[s][1]) >= MOVED_BY - 1e-9]
    return {"previous_on": str(prev_on) if prev_on else None, "new": new, "changed": changed, "dropped": dropped, "moved": moved,
            "sentence": plain.since(new, changed, dropped, moved) if prev_on else "This is the first set of calls."}


def unusual(db, as_of: date, scope, names, held, watch, cards, dist_200dma) -> list:
    """Stocks the father owns, watches or has a call on, where something out of the ordinary happened today."""
    scope = sorted(scope)
    if not scope:
        return []
    found: dict = {s: [] for s in scope}
    vols: dict = {}
    for sym, day, vol in db.execute("select symbol, date, volume from prices where exchange = 'NSE' and date <= ? and date > ? "
                                    "and symbol in (select unnest(?)) order by symbol, date", [as_of, as_of - timedelta(days=45), scope]).fetchall():
        vols.setdefault(sym, []).append(vol or 0)
    for sym, v in vols.items():
        before = [x for x in v[-21:-1] if x]
        if len(before) >= 5 and v[-1] and v[-1] / (sum(before) / len(before)) >= VOLUME_TIMES:
            found[sym].append(("volume", f"Trading {v[-1] / (sum(before) / len(before)):.1f} times its usual volume"))
    for sym in scope:
        d = dist_200dma.get(sym)
        if d is not None and abs(d) < AT_TREND:
            found[sym].append(("at_trend", "Price is right at its long-term trend line"))
    start = datetime.combine(as_of - timedelta(days=SOON_DAYS), time.min)
    for sym, subject in db.execute("select symbol, subject from announcements where announced_at >= ? and symbol in (select unnest(?)) "
                                   "order by announced_at desc, subject", [start, scope]).fetchall():
        low = subject.lower()
        if any(k in low for k in ACTION_WORDS) and not any(k == "corporate_action" for k, _ in found[sym]):
            found[sym].append(("corporate_action", "A dividend, split, bonus or similar was announced"))
        if "result" in low and not any(k == "results" for k, _ in found[sym]):
            found[sym].append(("results", "Results are coming"))
    for sym, on in db.execute("select symbol, min(date) from results_calendar where date >= ? and date <= ? and symbol in (select unnest(?)) "
                              "group by symbol", [as_of, as_of + timedelta(days=SOON_DAYS), scope]).fetchall():
        if not any(k == "results" for k, _ in found[sym]):
            found[sym].append(("results", f"Results are due on {on:%d %b}"))
    _, prev = previous_calls(db, as_of)
    for c in cards:
        old = prev.get(c["symbol"])
        if old and old[1] is not None and c["probability"] is not None and abs(c["probability"] - old[1]) >= MOVED_BY - 1e-9 and c["symbol"] in found:
            found[c["symbol"]].append(("forecast_moved", f"Our chance moved from {old[1]:.0%} to {c['probability']:.0%}"))
    snaps = [d for d, in db.execute("select distinct as_of from surveillance where as_of <= ? order by as_of desc limit 2", [as_of]).fetchall()]
    if len(snaps) == 2:
        now = {s for s, in db.execute("select symbol from surveillance where as_of = ?", [snaps[0]]).fetchall()}
        then = {s for s, in db.execute("select symbol from surveillance where as_of = ?", [snaps[1]]).fetchall()}
        for sym in sorted((now - then) & set(scope)):
            found[sym].append(("watch_list_entry", "The exchange put it on its close-watch list today"))
    rows = [{"symbol": s, "name": names.get(s, s), "held": s in held, "watchlist": s in watch,
             "signals": [{"kind": k, "text": t} for k, t in sig]} for s, sig in found.items() if sig]
    rows.sort(key=lambda r: (-len(r["signals"]), r["symbol"]))
    return rows
