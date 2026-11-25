"""His own record: what the father's own stock trades (not smallcase's) have shown over the years. Monthly page
`site/data/own_record.json`, and two plain lines in the market block of the brief: a fact about him, never about a stock.

A trade here is one sale: a sale that used several lots counts once, with the gain added up and the holding days
averaged by quantity. Only closed trades count; what is still held says nothing yet."""
import json
from datetime import date, timedelta
from pathlib import Path

from stockpilot.book import pairs as pairing

MIN_TRADES = 3          # fewer closed trades than this say nothing yet
LATER_DAYS = 91         # "the next 3 months"


def _trades(pairs, as_of: date):
    """One row per sale: cost, proceeds, quantity, average holding days, and the lots' dates (for the Nifty)."""
    grouped: dict = {}
    for p in pairs:
        if p["route"] != "kite" or p["sold_on"] > as_of:
            continue
        grouped.setdefault((p["symbol"], p["sold_on"]), []).append(p)
    out = []
    for (symbol, sold_on), rows in sorted(grouped.items(), key=lambda kv: kv[0][1]):
        qty = sum(r["quantity"] for r in rows)
        out.append({"symbol": symbol, "sold_on": sold_on, "quantity": qty, "cost": sum(r["cost"] for r in rows),
                    "proceeds": sum(r["proceeds"] for r in rows), "gain": sum(r["gain"] for r in rows),
                    "days": sum((r["sold_on"] - r["acquired_on"]).days * r["quantity"] for r in rows) / qty,
                    "lots": [(r["acquired_on"], r["cost"]) for r in rows]})
    return out


def _avg(values):
    return round(sum(values) / len(values), 1) if values else None


def build(db, as_of: date) -> dict:
    _, _, pairs = pairing.load(db)
    trades = _trades(pairs, as_of)
    winners = [t for t in trades if t["gain"] > 0]
    losers = [t for t in trades if t["gain"] <= 0]
    out = {"as_of": str(as_of), "closed": len(trades), "winners": len(winners), "losers": len(losers),
           "win_rate": round(100 * len(winners) / len(trades), 1) if trades else None,
           "avg_days_winners": _avg([t["days"] for t in winners]), "avg_days_losers": _avg([t["days"] for t in losers]),
           "sold_early": {"checked": 0, "rose_after": 0, "share": None},
           "vs_nifty": {"checked": 0, "beat": 0, "share": None, "average_gap_points": None},
           "by_month": [], "lines": []}
    if not trades:
        return out

    prices = pairing.prices_for(db, {t["symbol"] for t in winners}, min(t["sold_on"] for t in winners)) if winners else {}
    for t in winners:
        later = t["sold_on"] + timedelta(days=LATER_DAYS)
        if later > as_of:
            continue
        price = prices[t["symbol"]].near(later)
        if price is None:
            continue
        out["sold_early"]["checked"] += 1
        out["sold_early"]["rose_after"] += price > t["proceeds"] / t["quantity"]
    se = out["sold_early"]
    se["share"] = round(100 * se["rose_after"] / se["checked"], 1) if se["checked"] else None

    index, gaps = pairing.nifty(db), []
    for t in trades:
        end = index.on(t["sold_on"])
        starts = [(index.on(on), cost) for on, cost in t["lots"]]
        if not end or not all(s for s, _ in starts) or not t["cost"]:
            continue
        nifty_return = sum(cost * (end / s - 1) for s, cost in starts) / t["cost"]
        gaps.append((t["proceeds"] / t["cost"] - 1 - nifty_return) * 100)
    vn = out["vs_nifty"]
    vn["checked"], vn["beat"] = len(gaps), sum(g > 0 for g in gaps)
    if gaps:
        vn["share"], vn["average_gap_points"] = round(100 * vn["beat"] / len(gaps), 1), round(sum(gaps) / len(gaps), 2)

    months: dict = {}
    for t in trades:
        m = months.setdefault(t["sold_on"].strftime("%Y-%m"), {"closed": 0, "winners": 0, "gain": 0.0})
        m["closed"] += 1
        m["winners"] += t["gain"] > 0
        m["gain"] += t["gain"]
    out["by_month"] = [{"month": k, "closed": v["closed"], "winners": v["winners"], "gain": round(v["gain"], 2)}
                       for k, v in sorted(months.items())]

    if len(trades) >= MIN_TRADES:
        out["lines"].append(f"Of the {len(trades)} stock trades you closed, {out['win_rate']:.0f}% made money. "
                            f"Winners were held {out['avg_days_winners']:.0f} days on average, losers {out['avg_days_losers']:.0f}."
                            if winners and losers else
                            f"Of the {len(trades)} stock trades you closed, {out['win_rate']:.0f}% made money.")
        if se["share"] is not None:
            said = "Half" if se["share"] == 50 else f"{se['share']:.0f}%"
            out["lines"].append(f"{said} of the winners you sold went on to gain more within the next 3 months.")
    return out


def write(db, out, as_of: date) -> dict:
    """`site/data/own_record.json`, a new page file (no existing JSON changes shape)."""
    body = build(db, as_of)
    path = Path(out) / "data" / "own_record.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, default=str, separators=(",", ":")))
    return body
