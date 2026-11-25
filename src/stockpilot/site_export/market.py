"""Market-wide files: index lines, fund flows, closed trades and calls with their results."""
from datetime import date, timedelta

from stockpilot.book import pairs as pairing, record as own_record
from stockpilot.calls import record as call_record
from stockpilot.site_export import plain
from stockpilot.site_export.io import write_json

INDEX_KEYS = {"nifty": "Nifty 50", "bank": "Nifty Bank", "mid": "NIFTY Midcap 100", "small": "Nifty Smallcap 250", "vix": "India VIX"}
INDEX_DAYS = 400
FLOW_DAYS = 60
LONG_TERM_DAYS = 365
OUTCOME_ROWS = 2000


def _near(rows, day):
    """The value on the last date at or before `day`, or None."""
    best = None
    for d, v in rows:
        if d <= day:
            best = v
    return best


def indices(db, as_of: date) -> dict:
    out = {}
    for key, name in INDEX_KEYS.items():
        rows = db.execute("select date, close from index_levels where name = ? and date <= ? and date >= ? and close is not null order by date",
                          [name, as_of, as_of - timedelta(days=INDEX_DAYS)]).fetchall()
        if not rows:
            continue
        now = rows[-1][1]
        month, year = _near(rows, rows[-1][0] - timedelta(days=30)), _near(rows, rows[-1][0] - timedelta(days=365))
        change = lambda old: round(now / old - 1, 4) if old else None   # noqa: E731
        out[key] = {"name": name, "dates": [str(d) for d, _ in rows], "close": [round(c, 2) for _, c in rows],
                    "change_1m": change(month), "change_1y": change(year),
                    "sentence": plain.vix(now) if key == "vix" else plain.index_line(name, change(month), change(year))}
    return out


def flows(db, as_of: date) -> dict | None:
    rows = db.execute("select date, category, buy_cr, sell_cr, net_cr from flows where date <= ? and date >= ? order by date, category",
                      [as_of, as_of - timedelta(days=FLOW_DAYS)]).fetchall()
    if not rows:
        return None
    totals: dict = {}
    for _, cat, buy, sell, net in rows:
        t = totals.setdefault(cat, {"buy_cr": 0.0, "sell_cr": 0.0, "net_cr": 0.0, "days": 0})
        t["buy_cr"] += buy or 0
        t["sell_cr"] += sell or 0
        t["net_cr"] += net or 0
        t["days"] += 1
    totals = {c: {k: round(v, 2) if k != "days" else v for k, v in t.items()} for c, t in sorted(totals.items())}
    days = len({r[0] for r in rows})
    return {"as_of": str(rows[-1][0]), "days": days,
            "rows": [{"date": str(d), "category": c, "buy_cr": b, "sell_cr": s, "net_cr": n} for d, c, b, s, n in rows],
            "totals": totals,
            "sentence": plain.flows(days, totals.get("FII", {}).get("net_cr"), totals.get("DII", {}).get("net_cr"))}


def trades_closed(db, as_of: date) -> dict:
    _, _, pairs = pairing.load(db)
    rows = []
    for t in sorted(own_record._trades(pairs, as_of), key=lambda t: (t["sold_on"], t["symbol"]), reverse=True):
        rows.append({"symbol": t["symbol"], "sold_on": str(t["sold_on"]), "days": round(t["days"]), "quantity": t["quantity"],
                     "cost": round(t["cost"], 2), "proceeds": round(t["proceeds"], 2), "gain": round(t["gain"], 2),
                     "term": "long" if t["days"] > LONG_TERM_DAYS else "short"})
    total = round(sum(r["gain"] for r in rows), 2)
    winners = sum(1 for r in rows if r["gain"] > 0)
    return {"as_of": str(as_of), "closed": len(rows), "winners": winners, "losers": len(rows) - winners, "total_gain": total,
            "sentence": plain.trades(len(rows), winners, total), "rows": rows}


def calls_outcomes(db, as_of: date) -> dict:
    """Every call that has a result, newest first: what we said, and whether it beat the Nifty after costs and tax."""
    cols = ["made_on", "symbol", "action", "probability", "base_rate", "entry", "stop", "target", "score_1m", "score_3m", "score_6m"]
    rows = db.execute(f"select {', '.join(cols)} from {call_record.LATEST} where made_on <= ? and "
                      "(score_1m is not null or score_3m is not null or score_6m is not null) "
                      f"order by made_on desc, symbol limit {OUTCOME_ROWS}", [as_of]).fetchall()
    word = lambda s: None if s is None else "beat" if s > 0 else "missed"   # noqa: E731
    out = [{"made_on": str(r[0]), "symbol": r[1], "action": r[2], "probability": None if r[3] is None else round(r[3], 3),
            "base_rate": None if r[4] is None else round(r[4], 3), "entry": r[5], "stop": r[6], "target": r[7],
            "score_1m": r[8], "score_3m": r[9], "score_6m": r[10],
            "outcome_1m": word(r[8]), "outcome_3m": word(r[9]), "outcome_6m": word(r[10])} for r in rows]
    got = call_record.summary(db)
    hit3 = got["3m"]["hit_rate"] if got["3m"]["n"] else None
    return {"as_of": str(as_of), "sentence": plain.outcomes(len(out), hit3), "rows": out}


def write_all(db, out, as_of: date) -> dict:
    write_json(out, "indices", indices(db, as_of))
    f = flows(db, as_of)
    write_json(out, "flows", f or {"as_of": None, "days": 0, "rows": [], "totals": {}, "sentence": plain.flows(0, None, None)})
    write_json(out, "trades_closed", trades_closed(db, as_of))
    write_json(out, "calls_outcomes", calls_outcomes(db, as_of))
    return {"flows": f}
