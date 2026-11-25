"""Turn the model's probabilities into calls. The model forecasts; this module alone decides buy, sell, trim, follow and
hold, sizes the trades, and says what tax a sale costs. Every threshold lives in config `rules:` (never in a prompt), and
the budget never touches a size: buys are sized by the risk rules alone.

Sections:
  buy     every stock at or above the buy line, best expected gain first, no cap on the count
  sell    a holding with something to act on, each call carrying a `sell_kind`:
            sell    its sell price was reached (the code-set stop, only on a position opened from a call), or the analyst
                    states that the reason for owning it has broken (`broken_reason`)
            weak    its chance is at or below the sell line and nothing else is wrong
            review  a holding marked "I hold this for years": it is judged over years, so none of the above sells it
          a holding under `min_sale_inr` never gets a sell. The call names the reason, shows the tax, and "Not now" hides it.
          Code facts (ASM/GSM, a lagging sector, one weak quarter) go to the analyst; they do not sell on their own.
  trim    a holding above the single-stock cap, cut back to the cap (sell_kind "sell")
  follow  the next best below the buy line, each with what would make it a buy
  hold    every other holding
  watch   analysed and logged for the record, not shown
"""
import math
from dataclasses import dataclass, field
from datetime import date

from stockpilot import costs

from stockpilot.analysis import tax

SECTION_ORDER = ["buy", "sell", "trim", "follow", "hold", "watch"]
LEARNED_EXCEPTION = 0.10     # R11: a buy this far above the buy line is never demoted by a learned pattern
ACTION_OF = {"buy": "buy", "sell": "sell", "trim": "trim", "follow": "watch", "hold": "hold", "watch": "watch"}


@dataclass(frozen=True)
class Rules:
    buy_at: float = 0.57             # buy or add at or above this probability
    sell_at: float = 0.40            # sell a holding at or below this
    borderline: float = 0.05         # within this of a line, the skeptic gets a say
    risk_per_trade: float = 0.01     # a stop-loss hit may cost at most this share of the portfolio
    max_single: float = 0.08         # no stock above this share of the portfolio
    follow_count: int = 10           # stocks worth following below the buy line
    watch_cap: int = 8               # triggered watchlist stocks sent to the model in one evening (analysis volume, not money)
    setaside_limit: int = 3          # set-asides in a sector, within setaside_days, that cap it at one buy a week
    setaside_days: int = 30
    sector_week_days: int = 7
    sector_warn_at: float = 0.20     # a buy that takes a sector to this share of the portfolio gets a warning line
    tax_wait_days: int = 30          # suggest waiting when a lot turns long-term this soon
    min_sale_inr: float = 5000.0     # a holding worth less than this never gets a sell: the fees outweigh the call
    stops_from: date = date(2026, 11, 24)    # code stops apply to positions opened from a call on or after this day
    stop_call_days: int = 5          # a position counts as opened from a call within this many trading days of it
    behind_sector: float = 0.20      # a thesis break: 20 points behind its sector index over three months
    results_miss: float = 0.25       # a thesis break: latest quarter's net profit down this much on the same quarter a year ago
    nifty_3m: float = 0.03           # the Nifty's assumed three-month return, for the hurdle
    sector_index: dict = field(default_factory=dict)   # industry -> index name in index_levels
    passive: tuple = ()              # index and gold funds held on purpose: never sold for failing to beat the Nifty

    def is_passive(self, symbol: str) -> bool:
        s = symbol.upper()
        return s in {x.upper() for x in self.passive} or s.endswith("BEES") or s.endswith("ETF")

    @classmethod
    def from_config(cls, cfg) -> "Rules":
        raw = dict(cfg.get("rules") or {})
        if "stops_from" in raw:
            raw["stops_from"] = date.fromisoformat(str(raw["stops_from"]))
        known = {k: v for k, v in raw.items() if k in cls.__dataclass_fields__ and k not in ("sector_index", "passive")}
        known["passive"] = tuple(raw.get("passive") or ())
        return cls(**known, sector_index=dict(cfg.get("sector_index") or {}))


def inr(x: float) -> str:
    x = abs(x)
    if x >= 1e7:
        v = f"{x / 1e7:.1f}".removesuffix(".0")
        return f"₹{v} crore"
    if x >= 1e5:
        v = f"{x / 1e5:.1f}".removesuffix(".0")
        return f"₹{v} lakh"
    return f"₹{x:,.0f}"


def _day(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def _tax_note(lots: list[dict], today: date, rules: Rules, qty: float | None = None) -> str | None:
    soon = [(l["turns_long_term_on"], l) for l in lots
            if l.get("turns_long_term_on") and today < l["turns_long_term_on"] <= today.fromordinal(today.toordinal() + rules.tax_wait_days)]
    if not soon:
        return None
    turns = min(t for t, _ in soon)
    shares = sum(l["quantity"] for t, l in soon if t == turns)
    r = tax.rules_for(tax.fy_of(today))
    return (f"{shares:g} shares turn long-term on {_day(turns)} ({(turns - today).days} days). "
            f"Waiting cuts tax from {r.stcg_equity_rate:.0%} to {r.ltcg_equity_rate:.1%}.")


def _fifo(lots: list[dict], qty: float) -> list[dict]:
    out, left = [], qty
    for l in sorted(lots, key=lambda l: l["acquired_on"]):
        take = min(left, l["quantity"])
        if take > 0:
            out.append({**l, "quantity": take})
            left -= take
    return out


def _tax_line(item: dict, qty: float, today: date, rules: Rules) -> str:
    price = item.get("price") or (item.get("levels") or {}).get("entry") or 0
    due = costs.tax_if_sold(_fifo(item["lots"], qty), price, today)["tax"] if price else 0
    head = f"Selling {qty:g} today: about {inr(due)} tax." if due else f"Selling {qty:g} today: no tax to pay."
    note = _tax_note(item["lots"], today, rules)
    return f"{head} {note}" if note else head


def _size(levels: dict | None, held_qty: float, pv: float, rules: Rules) -> tuple[int, str | None]:
    if not levels or pv <= 0:
        return 0, None
    entry, stop = levels["entry"], levels["stop"]
    if not entry or entry <= 0 or not stop or stop >= entry:
        return 0, None
    cap = max(0, math.floor(rules.max_single * pv / entry) - math.floor(held_qty))
    risk = math.floor(rules.risk_per_trade * pv / (entry - stop))
    return (cap, "cap") if cap <= risk else (risk, "risk")


def borderline(items: list[dict], rules: Rules) -> list[str]:
    return [i["symbol"] for i in items
            if min(abs(i["probability"] - rules.buy_at), abs(i["probability"] - rules.sell_at)) <= rules.borderline + 1e-9]


def _stop(item: dict, call: dict) -> float:
    """The stop that was hit: the one set when the position was opened (`stop_hit` carries it), else tonight's."""
    hit = item.get("stop_hit")
    return hit if isinstance(hit, (int, float)) and not isinstance(hit, bool) else call["stop"]


def _call(item: dict) -> dict:
    keep = ["symbol", "name", "industry", "kind", "broken_reason", "probability", "raw_probability", "base_rate", "base_rate_n", "hurdle", "summary", "summary_bn",
            "moved_by", "risks", "news_used", "level_flag", "change_reason", "would_buy_if", "for", "against", "unknowns"]
    c = {k: item.get(k) for k in keep}
    lv = item.get("levels") or {}
    c.update(entry=lv.get("entry"), stop=lv.get("stop"), target=lv.get("target"), levels_why=lv.get("why"),
             target_hit_rate=lv.get("target_hit_rate"), target_hit_n=lv.get("target_hit_n"),
             quantity=0, amount=0.0, sized_by=None, expected_gain_inr=None, tax_line=None, tax_note=None, warnings=[],
             since=None, since_text=None, why_code=None, borderline=False, blocked=None, sell_kind=None)
    if lv.get("entry") and lv.get("stop") and lv.get("target"):
        c["upside_pct"] = round(100 * (lv["target"] - lv["entry"]) / lv["entry"], 1)
        c["downside_pct"] = round(100 * (lv["entry"] - lv["stop"]) / lv["entry"], 1)
    return c


def sections(items: list[dict], *, rules: Rules, day: date, portfolio_value: float, sector_values: dict,
             block_buys: str | None, not_now: list[tuple[str, str]], setasides: dict, recent_sector_buys: dict) -> dict:
    """Each item: symbol, name, industry, probability, kind, held_qty, price, levels (entry, stop, target, why) or None,
    adv_cr, hurdle, lots, stop_hit, buy_since, and the model's words. `not_now` holds the active (symbol, scope) pairs."""
    hidden = {"buy": {s for s, sc in not_now if sc in ("buy", "any")}, "sell": {s for s, sc in not_now if sc in ("sell", "any")}}
    calls, buys = [], []
    near = set(borderline(items, rules))
    for item in items:
        p, held, sym = item["probability"], item.get("held_qty") or 0, item["symbol"]
        c = _call(item)
        c["borderline"] = c["symbol"] in near
        price = item.get("price") or c["entry"] or 0
        cap_qty = rules.max_single * portfolio_value / price if price else 0
        qty, by = _size(item.get("levels"), held, portfolio_value, rules)
        if qty and c["entry"]:
            c["expected_gain_inr"] = round(costs.expected_gain(qty, c["entry"], c["stop"], c["target"], p, item.get("adv_cr"))["net"])
        if held:
            c["quantity"] = 0
            sell_hidden = sym in hidden["sell"]
            passive = bool(item.get("passive"))
            broken = "" if passive else str(item.get("broken_reason") or "").strip()
            low = p <= rules.sell_at and not passive
            stopped = bool(item.get("stop_hit"))
            sell_cause = low or stopped or bool(broken)
            tiny = price * held < rules.min_sale_inr
            if sell_cause and not sell_hidden and not tiny:
                years = bool(item.get("long_term"))
                if stopped and not low:
                    why = f"It fell to its stop (₹{_stop(item, c):,.0f})."
                elif low:
                    why = f"Its chance is {p:.0%}, at or below the {rules.sell_at:.0%} sell line."
                else:
                    why = ""
                if broken:
                    why = f"{why} The reason for owning it has broken: {broken.rstrip('.')}.".strip()
                kind = "review" if years else "sell" if (stopped or broken) else "weak"
                if kind == "sell" and stopped and not low and not broken:
                    why += " Sell."
                if kind == "review":
                    why += " You hold this for years, so this is a review, not a sale."
                elif kind == "weak":
                    why += " That alone is weak, not a sell: nothing has broken."
                c.update(section="sell", sell_kind=kind, quantity=held, expected_gain_inr=None,
                         tax_line=_tax_line(item, held, day, rules), tax_note=_tax_note(item["lots"], day, rules), why_code=why)
            elif portfolio_value > 0 and price and held > cap_qty and not sell_hidden and not tiny:
                excess = held - math.floor(cap_qty)
                c.update(section="trim", sell_kind="sell", quantity=excess, expected_gain_inr=None, tax_line=_tax_line(item, excess, day, rules),
                         tax_note=_tax_note(item["lots"], day, rules),
                         why_code=f"It is {100 * held * price / portfolio_value:.1f}% of the portfolio; the limit is {rules.max_single:.0%}.")
            elif p >= rules.buy_at and qty and sym not in hidden["buy"] and not block_buys:
                c.update(section="buy", action="add", quantity=qty, sized_by=by, amount=round(qty * c["entry"], 2),
                         why_code=f"Its chance is {p:.0%}, at or above the {rules.buy_at:.0%} buy line.")
                buys.append(c)
            else:
                c["section"] = "hold"
                if p >= rules.buy_at and block_buys:
                    c["warnings"].append(block_buys)
                if sell_hidden and sell_cause:
                    c["warnings"].append("You set this sell aside for now.")
                elif tiny and sell_cause:
                    c["warnings"].append(f"Worth under {inr(rules.min_sale_inr)}: too small to be worth a sale.")
        else:
            if p >= rules.buy_at and sym not in hidden["buy"]:
                if block_buys:
                    c.update(section="follow", blocked=block_buys)
                    c["warnings"].append(block_buys)
                elif not qty:
                    c.update(section="follow", blocked="No size can be set")
                    c["warnings"].append("No size can be set: the price levels or the portfolio value are missing.")
                elif item.get("learned") and round(p - rules.buy_at, 6) < LEARNED_EXCEPTION:
                    # R11: like stocks the owners set aside. Demoted, never removed; a strong chance still buys.
                    c.update(section="follow", blocked=None)
                    c["warnings"].append(f"Like stocks you set aside ({item['learned']})")
                    c["change_reason"] = f"learned: {item['learned']}"
                    c["would_buy_if"] = c["would_buy_if"] or f"Its chance is {p:.0%}; {rules.buy_at + LEARNED_EXCEPTION:.0%} or more would buy it anyway."
                else:
                    c.update(section="buy", quantity=qty, sized_by=by, amount=round(qty * c["entry"], 2),
                             why_code=f"Its chance is {p:.0%}, at or above the {rules.buy_at:.0%} buy line.")
                    buys.append(c)
            elif sym in hidden["buy"]:
                c["section"] = "watch"
            else:
                c["section"] = "follow"
        if c.get("section") == "follow" and not c["would_buy_if"] and c["blocked"]:
            c["would_buy_if"] = c["blocked"]
        c.setdefault("action", ACTION_OF[c["section"]])
        if c["section"] == "buy" and item.get("buy_since"):
            c["since"] = str(item["buy_since"])
            c["since_text"] = f"a buy since {item['buy_since'].day} {item['buy_since']:%b}"
        calls.append(c)

    notes = _sector_rule(buys, rules, setasides, recent_sector_buys)
    _sector_warnings([c for c in buys if c["section"] == "buy"], sector_values, portfolio_value, rules)
    follow = [c for c in calls if c["section"] == "follow"]
    follow.sort(key=lambda c: -c["probability"])
    for c in follow[rules.follow_count:]:
        c["section"], c["action"] = "watch", "watch"
    rank = {s: i for i, s in enumerate(SECTION_ORDER)}
    calls.sort(key=lambda c: (rank[c["section"]], -(c["expected_gain_inr"] or 0) if c["section"] == "buy" else -c["probability"]))
    return {"calls": calls, "sector_notes": notes}


def _sector_rule(buys: list[dict], rules: Rules, setasides: dict, recent: dict) -> list[str]:
    """A sector with three or more set-asides in 30 days shows at most one buy a week."""
    notes = []
    for sector, n in setasides.items():
        if n < rules.setaside_limit:
            continue
        mine = sorted((c for c in buys if c["industry"] == sector and c["section"] == "buy"),
                      key=lambda c: -(c["expected_gain_inr"] or 0))
        notes.append(f"{sector}: {n} set aside in the last {rules.setaside_days} days, so at most one {sector} buy a week.")
        if not mine:
            continue
        carry = [c for c in mine if c["symbol"] in recent.get(sector, set())]
        keep = carry[:1] if recent.get(sector) else mine[:1]
        for c in mine:
            if c not in keep:
                c.update(section="follow", action="watch", quantity=0, amount=0.0, sized_by=None, why_code=None, since=None,
                         since_text=None)
                c["warnings"].append(f"{sector}: at most one buy a week here, because you set {n} aside this month.")
                if not c["would_buy_if"]:
                    c["would_buy_if"] = "A week after the last " + sector + " buy."
    return notes


def _sector_warnings(buys: list[dict], sector_values: dict, pv: float, rules: Rules) -> None:
    if pv <= 0:
        return
    running = dict(sector_values)
    for c in sorted(buys, key=lambda c: -(c["expected_gain_inr"] or 0)):
        sector = c["industry"]
        if not sector:
            continue
        before = running.get(sector, 0.0) / pv
        after = (running.get(sector, 0.0) + c["amount"]) / pv
        running[sector] = running.get(sector, 0.0) + c["amount"]
        if after >= rules.sector_warn_at and after > before:
            c["warnings"].append(f"{before:.0%} in {sector}; this makes it {after:.0%}.")


def budget_line(left: float, amounts: list[float]) -> str | None:
    """Where the month's budget lands: how many of tonight's buys, best first, it covers. Information only."""
    if not amounts:
        return None
    spent, k = 0.0, 0
    for a in amounts:
        if spent + a > left:
            break
        spent, k = spent + a, k + 1
    if k == 0:
        return f"{inr(left)} left does not cover the first buy"
    return f"{inr(left)} left covers the first {k}"
