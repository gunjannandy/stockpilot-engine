"""The RSU pane and the ServiceNow page, as data: what the shares cost, what they are worth, where each lot came from,
when each turns long-term, what a sale would cost in tax, and the concentration call. Everything in rupees, every lot
labelled real (Fidelity's statement or a vest document) or estimated. The call is advice in words, never an order.

Tax on a US share (the tax module's foreign bucket): long-term only after 24 months, taxed at the other-assets rate; a
short-term gain is taxed at the slab. The slab is unknown here, so the short-term rate is the top slab, which makes the
figure an upper bound. Cess 4% on both; surcharge and the sale-day rate rule are left out ("about")."""
import math
from datetime import date

from stockpilot.analysis import tax
from stockpilot.calls.decide import inr
from stockpilot.sources import fx

SYMBOL, NAME = "NOW", "ServiceNow"
SLAB_TOP = 0.30


def _origin(source: str, estimated: bool) -> str:
    return "estimate" if estimated else "statement" if "fidelity_statement" in (source or "") else "document"


def _tax(gains: dict, rules: tax.TaxRules) -> dict:
    short, long_ = gains["short"], gains["long"]
    if short < 0:                       # a short-term loss is set off against the long-term gain
        long_, short = long_ + short, 0.0
    long_ = max(long_, 0.0)
    due = (long_ * rules.ltcg_other_rate + short * SLAB_TOP) * (1 + rules.cess)
    return {"short_gain_inr": round(short, 2), "long_gain_inr": round(long_, 2), "tax_inr": round(due, 2),
            "net_gain_inr": round(gains["short"] + gains["long"], 2)}


def _gains(lots: list[dict], price_inr: float) -> dict:
    out = {"short": 0.0, "long": 0.0}
    for l in lots:
        out[l["term"]] += l["quantity"] * price_inr - l["cost_inr"]
    return out


def build(db, today: date, *, price_usd: float | None, portfolio_value: float, max_single: float, symbol: str = SYMBOL) -> dict | None:
    rows = db.execute("select acquired_on, quantity - closed_quantity, cost_per_unit, coalesce(currency, 'USD'), source, "
                      "coalesce(estimated, false) from lots where kind = 'rsu' and symbol = ? and quantity - closed_quantity > 1e-9 "
                      "order by acquired_on, id", [symbol]).fetchall()
    if not rows:
        return None
    rate_on = fx.rate_on(db)
    rate = fx.usdinr_on(db, today) or 0.0
    lots = []
    for day, qty, cost, cur, source, est in rows:
        r = (rate_on(day) or rate) if cur != "INR" else 1.0
        turns = tax.turns_long_term_on("foreign", day)
        lots.append({"acquired_on": str(day), "quantity": qty, "cost_inr": qty * cost * r, "origin": _origin(source, est),
                     "term": "long" if turns and today >= turns else "short", "turns_long_term_on": str(turns),
                     "days_to_long_term": max((turns - today).days, 0) if turns else None})
    shares = sum(l["quantity"] for l in lots)
    cost_inr = sum(l["cost_inr"] for l in lots)
    price_inr = (price_usd or 0.0) * rate
    for l in lots:
        l["cost_per_share_inr"] = l["cost_inr"] / l["quantity"]
        l["value_inr"] = l["quantity"] * price_inr if price_inr else None
        l["gain_inr"] = l["value_inr"] - l["cost_inr"] if price_inr else None
    value = shares * price_inr
    stmt = db.execute("select max(as_of) from fidelity_lots where symbol = ?", [symbol]).fetchone()[0]
    est_shares = sum(l["quantity"] for l in lots if l["origin"] == "estimate")
    rules = tax.rules_for(tax.fy_of(today))
    out = {"symbol": symbol, "name": NAME, "shares": shares, "price_usd": price_usd, "usd_inr": rate or None,
           "cost_inr": cost_inr, "value_inr": value if price_inr else None,
           "profit_inr": value - cost_inr if price_inr else None,
           "profit_pct": (value / cost_inr - 1) if price_inr and cost_inr else None,
           "share_of_portfolio": value / portfolio_value if price_inr and portfolio_value else None, "limit": max_single,
           "lots": lots, "vests": [{k: l[k] for k in ("acquired_on", "quantity", "origin")} for l in sorted(lots, key=lambda l: l["acquired_on"], reverse=True)],
           "expected_vests": [{"date": str(d), "quantity": q, "status": "expected"} for d, q in db.execute(
               "select trade_date, quantity from trades where kind = 'rsu' and symbol = ? and status = 'expected' and trade_date >= ? "
               "order by trade_date", [symbol, today]).fetchall()],
           "statement": {"as_of": str(stmt) if stmt else None, "real_shares": shares - est_shares, "estimated_shares": est_shares,
                         "note": ("All shares are real: Fidelity's list and vest documents add up to its count." if not est_shares else
                                  f"{est_shares:g} shares came after the last document. They are an estimate until Fidelity sends a new list.")},
           "tax_if_sold": None, "call": None}
    if not price_inr:
        return out
    out["tax_if_sold"] = {"all": _tax(_gains(lots, price_inr), rules),
                          "note": "Upper bound: top tax slab for short-term, 12.5% for long-term, 4% cess, today's rate."}
    over = value - max_single * portfolio_value
    if portfolio_value > 0 and over > 0:
        n = min(shares, math.ceil(over / ((1 - max_single) * price_inr)))
        sold, left = [], n
        for l in lots:                              # oldest first, like the tax module
            take = min(left, l["quantity"])
            if take > 0:
                sold.append({**l, "quantity": take, "cost_inr": l["cost_inr"] * take / l["quantity"]})
                left -= take
        t = _tax(_gains(sold, price_inr), rules)
        out["tax_if_sold"]["trim"] = {**t, "shares": n}
        pct = value / portfolio_value
        out["call"] = {"stance": "trim", "shares": n, "sells_oldest_first": True,
                       "why": f"{NAME} is {pct:.0%} of everything you own. The limit is {max_single:.0%}. Selling about {n:g} shares would bring it to the limit.",
                       "tax_line": (f"Selling {n:g} shares today: no tax to pay. It would book a loss of about {inr(-t['net_gain_inr'])} "
                                    "that you can set against other gains." if t["net_gain_inr"] < 0 and not t["tax_inr"] else
                                    f"Selling {n:g} shares today: about {inr(t['tax_inr'])} tax"
                                    f" ({inr(t['long_gain_inr'])} long-term gain, {inr(t['short_gain_inr'])} short-term gain).")
                                   + " This is a view for you to weigh; nothing is sold for you."}
    return out
