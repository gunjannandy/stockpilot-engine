"""Smallcase against Kite, per holding and over time. A holding is just a stock; this only shows how much of it
came in through each route. The tag sits on each trade (`trade_tags`, see trades/smallcase.py)."""
import json
from datetime import date, timedelta
from pathlib import Path

from stockpilot.analysis import tax
from stockpilot.book import pairs as pairing


def held_by_source(db, positions) -> dict:
    """{symbol: {"kite": qty, "smallcase": qty, "baskets": {basket: qty}}} for each position in `positions`.
    Quantity comes from the open lots, tagged by the trade that bought them. Free shares from a bonus or a
    demerger follow the same split as the lots they came from; any quantity the lots do not hold (a holding only
    Kite or the depository shows) counts as Kite."""
    out = {}
    for p in positions:
        key = p.isin or p.symbol
        rows = db.execute(
            "select l.source_ref, l.quantity - l.closed_quantity, t.placed_by, t.basket from lots l "
            "left join trade_tags t on t.trade_key = l.source_ref "
            "where coalesce(l.isin, l.symbol) = ? and l.quantity - l.closed_quantity > 1e-9", [key]).fetchall()
        tagged = {"kite": 0.0, "smallcase": 0.0}
        baskets: dict[str, float] = {}
        free = 0.0
        for ref, open_qty, placed_by, basket in rows:
            if placed_by is None:
                free += open_qty if str(ref).split(":")[0] in ("bonus", "demerger") else 0.0
                tagged["kite"] += 0.0 if str(ref).split(":")[0] in ("bonus", "demerger") else open_qty
                continue
            tagged[placed_by] += open_qty
            if placed_by == "smallcase" and basket:
                baskets[basket] = baskets.get(basket, 0.0) + open_qty
        base = tagged["kite"] + tagged["smallcase"]
        if free and base:   # free shares share the split of what they came from
            scale = (base + free) / base
            tagged = {k: v * scale for k, v in tagged.items()}
            baskets = {b: v * scale for b, v in baskets.items()}
        elif free:
            tagged["kite"] += free
        rest = p.quantity - tagged["kite"] - tagged["smallcase"]
        if rest > 1e-6:
            tagged["kite"] += rest
        out[p.symbol] = {"kite": round(tagged["kite"], 6), "smallcase": round(tagged["smallcase"], 6),
                         "baskets": {b: round(v, 6) for b, v in baskets.items()}}
    return out


# --- smallcase against Dad's own trades and the Nifty --------------------------------------------

YEARLY_FEE = 6000          # smallcase's subscription, per year
REBALANCE_FEE = 100        # per rebalance, plus tax on that fee
TAX_ON_FEE = 0.18          # GST on the per-rebalance fee
TAX_YEAR_FOR_RATES = 2024  # one rate set for every year: the rates before July 2024 were different (see status R8)


def _month_ends(first: date, as_of: date):
    y, m = first.year, first.month
    while (y, m) <= (as_of.year, as_of.month):
        last = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        yield min(last, as_of)
        y, m = y + (m == 12), m % 12 + 1


def _tax_by_route(pairs, upto: date, rules) -> dict:
    """Capital-gains tax on what each route sold up to `upto`: short-term at the short rate, long-term above the
    yearly exemption, which the two routes share in proportion to their long-term gains. A loss in one year or
    route is not set against a gain elsewhere."""
    per: dict = {}
    for p in pairs:
        if p["sold_on"] > upto:
            continue
        cell = per.setdefault((tax.fy_of(p["sold_on"]), p["route"]), {"short": 0.0, "long": 0.0})
        cell[p["term"]] += p["gain"]
    out = {"smallcase": 0.0, "kite": 0.0}
    for fy in {fy for fy, _ in per}:
        long_gains = {r: max(per.get((fy, r), {}).get("long", 0.0), 0.0) for r in out}
        total_long = sum(long_gains.values())
        for route in out:
            cell = per.get((fy, route), {"short": 0.0, "long": 0.0})
            share = rules.ltcg_exempt * long_gains[route] / total_long if total_long else 0.0
            out[route] += (rules.stcg_equity_rate * max(cell["short"], 0.0)
                           + rules.ltcg_equity_rate * max(cell["long"] - share, 0.0)) * (1 + rules.cess)
    return out


def _rs(x: float) -> str:
    return f"₹{abs(x):,.0f}" if x >= 0 else f"a loss of ₹{abs(x):,.0f}"


def comparison(db, as_of: date) -> dict:
    """What smallcase delivered, month by month since its first trade, after its fees and tax, against Dad's own
    trades over the same months and against the same money put into the Nifty on the same days."""
    fees = {"yearly": YEARLY_FEE, "per_rebalance": REBALANCE_FEE, "tax_on_fees": TAX_ON_FEE}
    empty = {"as_of": str(as_of), "fees": fees, "months": [], "lines": [], "notes": []}
    rebalance_days = sorted(d for (d,) in db.execute(
        "select distinct t.trade_date from trades t join trade_tags g on g.trade_key = t.trade_key "
        "where g.placed_by = 'smallcase' and t.trade_date <= ?", [as_of]).fetchall())
    if not rebalance_days:
        return empty
    start = rebalance_days[0].replace(day=1)
    lots, _, pairs = pairing.load(db)
    lots = [l for l in lots if l["acquired_on"] >= start and l["acquired_on"] <= as_of]
    pairs = [p for p in pairs if p["acquired_on"] >= start]
    prices = pairing.prices_for(db, {l["symbol"] for l in lots}, start)
    index = pairing.nifty(db)
    rules = tax.rules_for(TAX_YEAR_FOR_RATES)
    unpriced: set = set()
    by_lot: dict = {}
    for p in pairs:
        by_lot.setdefault(p["lot_id"], []).append(p)
    months = []
    for end in _month_ends(start, as_of):
        row: dict = {"month": end.strftime("%Y-%m")}
        taxes = _tax_by_route(pairs, end, rules)
        n_months = (end.year - start.year) * 12 + end.month - start.month + 1
        for route, label in (("smallcase", "smallcase"), ("kite", "own")):
            invested = realised = unrealised = nifty_gain = 0.0
            for lot in (l for l in lots if l["route"] == route and l["acquired_on"] <= end):
                cost = lot["quantity"] * lot["cost_per_unit"]
                invested += cost
                base = index.on(lot["acquired_on"])
                sold = 0.0
                for p in (p for p in by_lot.get(lot["id"], []) if p["sold_on"] <= end):
                    sold += p["quantity"]
                    realised += p["gain"]
                    if base and (then := index.on(p["sold_on"])):
                        nifty_gain += p["quantity"] * lot["cost_per_unit"] * (then / base - 1)
                left = lot["quantity"] - sold
                if left > 1e-9:
                    price = prices[lot["symbol"]].on(end)
                    if price is None:
                        unpriced.add(lot["symbol"])
                    else:
                        unrealised += left * (price - lot["cost_per_unit"])
                    if base and (now := index.on(end)):
                        nifty_gain += left * lot["cost_per_unit"] * (now / base - 1)
            fee = 0.0
            if route == "smallcase":
                fee = YEARLY_FEE / 12 * n_months + REBALANCE_FEE * (1 + TAX_ON_FEE) * sum(d <= end for d in rebalance_days)
            gain = realised + unrealised
            paid_tax = taxes[route]
            after = gain - fee - paid_tax
            row[label] = {"invested": round(invested, 2), "gain": round(gain, 2), "realised": round(realised, 2),
                          "unrealised": round(unrealised, 2), "fees": round(fee, 2), "tax": round(paid_tax, 2),
                          "after_fees_and_tax": round(after, 2), "nifty_gain": round(nifty_gain, 2),
                          "return_pct": round(100 * after / invested, 2) if invested else None,
                          "nifty_pct": round(100 * nifty_gain / invested, 2) if invested else None}
        months.append(row)
    last = months[-1]
    sc, own = last["smallcase"], last["own"]
    lines = [f"Since {start:%B %Y}, the smallcase trades gained {_rs(sc['gain'])} before costs. After fees of "
             f"{_rs(sc['fees'])} and tax of {_rs(sc['tax'])}, that is {_rs(sc['after_fees_and_tax'])}.",
             f"The same money put into the Nifty on the same days would have gained {_rs(sc['nifty_gain'])}, before tax.",
             f"Your own trades over the same months gained {_rs(own['gain'])} before tax; after tax of {_rs(own['tax'])}, "
             f"{_rs(own['after_fees_and_tax'])}. The same money in the Nifty: {_rs(own['nifty_gain'])}, before tax."]
    notes = ["Fees are ₹6,000 a year plus ₹100 and 18% tax on each rebalance day.",
             "Tax uses today's rates for every year, and a loss in one route is not set against a gain in the other."]
    if unpriced:
        notes.append(f"No price found for {len(unpriced)} stocks, so they count at cost: {', '.join(sorted(unpriced)[:5])}.")
    return {"as_of": str(as_of), "since": str(start), "fees": fees, "months": months, "lines": lines, "notes": notes}


def write(db, out, as_of: date) -> None:
    """`site/data/smallcase.json`, a new page file (no existing JSON changes shape)."""
    path = Path(out) / "data" / "smallcase.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(comparison(db, as_of), default=str, separators=(",", ":")))
