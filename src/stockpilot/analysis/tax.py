"""Indian capital-gains and income-tax maths for a resident individual on the new regime.
Pure functions over plain dicts, so every rule is testable on its own. Rules and section numbers come
from docs/research/tax-rules.md; anything it marks unconfirmed is a parameter here, not a hard-coded guess."""
import csv
import json
import math
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

from stockpilot.book import kinds

GRANDFATHER_DATE = date(2018, 2, 1)          # lots bought before this use the 31 Jan 2018 value
SPECIFIED_MF_FROM = date(2023, 4, 1)         # debt-fund units bought on or after this are always short-term
CARRY_YEARS = 8
MONTHS = {"equity": 12, "gold_etf": 12, "other": 24, "foreign": 24}   # long-term only after MORE than this
SHORT_POOLS = ("stcg_slab", "stcg_equity")   # a short-term loss is set off in this order, then against long-term gains
LONG_POOLS = ("ltcg_other", "ltcg_equity")   # other-rate gains first, so the Rs 1.25 lakh exemption is not wasted


class OversoldError(ValueError):
    """A sale has no lot to match: the lots on file are incomplete, so any gain would be a guess."""


class MissingRate(ValueError):
    pass


@dataclass(frozen=True)
class TaxRules:
    ltcg_exempt: float = 125_000
    stcg_equity_rate: float = 0.20           # s.196
    ltcg_equity_rate: float = 0.125          # s.198, above the exemption
    ltcg_other_rate: float = 0.125           # s.197
    slabs: tuple = ((400_000, 0.0), (800_000, 0.05), (1_200_000, 0.10), (1_600_000, 0.15),
                    (2_000_000, 0.20), (2_400_000, 0.25), (float("inf"), 0.30))
    standard_deduction: float = 75_000
    rebate_limit: float = 1_200_000
    rebate_max: float = 60_000
    cess: float = 0.04
    surcharge_from: float = 5_000_000
    surcharge_tiers: tuple = ((20_000_000, 0.25), (10_000_000, 0.15), (5_000_000, 0.10))   # income above, rate (no 37% in the new regime)
    surcharge_cap_gains: float = 0.15        # on dividends and s.196/197/198 gains


def rules_for(tax_year: int) -> TaxRules:
    """One rule set today: the 2025 Act re-enacts the 1961 rates for FY 2026-27, and FY 2024-25 onward share them."""
    if tax_year < 2024:
        raise ValueError(f"no rule set for FY {tax_year}-{(tax_year + 1) % 100:02d}: capital-gains rates differ before July 2024")
    return TaxRules()


def fy_of(day: date) -> int:
    return day.year if day.month >= 4 else day.year - 1


def fy_label(fy: int) -> str:
    return f"{fy}-{(fy + 1) % 100:02d}"


def _add_months(day: date, months: int) -> date:
    y, m = divmod(day.month - 1 + months, 12)
    year, month = day.year + y, m + 1
    last = (date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)).day
    return date(year, month, min(day.day, last))


def _month_end_before(day: date) -> date:
    return day.replace(day=1) - timedelta(days=1)


# --- classification ---------------------------------------------------------------------------

def mf_bucket(category: str | None, acquired_on: date, name: str = "") -> str:
    """Which tax bucket a fund unit falls in. Unknown funds go to 'other' (24 months, 12.5%): the cautious reading."""
    c, n = (category or "").lower(), name.lower()
    if c.startswith("equity scheme"):
        return "equity"
    if c.startswith("hybrid scheme"):
        return "equity" if any(k in c for k in ("arbitrage", "aggressive", "equity savings", "multi asset")) \
            and "balanced" not in c else "other"
    if "gold" in c or "gold" in n:
        return "gold_etf" if "etf" in c or "etf" in n else "other"
    if c.startswith("debt scheme"):
        return "specified_mf" if acquired_on >= SPECIFIED_MF_FROM else "other"
    if ("index" in c or "etf" in c) and any(k in n for k in ("nifty", "sensex", "bse 500", "equity")) \
            and "overseas" not in c and "debt" not in n and "gilt" not in n:
        return "equity"
    return "other"


def bucket_of(lot: dict) -> str:
    if lot.get("bucket"):
        return lot["bucket"]
    if kinds.is_foreign(lot):
        return "foreign"
    return "equity" if kinds.canon(lot.get("kind") or "equity") == "equity" else "other"


def term(bucket: str, acquired_on: date, sold_on: date) -> str:
    if bucket == "specified_mf":
        return "short"
    return "long" if sold_on > _add_months(acquired_on, MONTHS[bucket]) else "short"


def turns_long_term_on(bucket: str, acquired_on: date) -> date | None:
    """The first day a sale is long-term: the day after the holding period ends. None for a bucket that never is."""
    if bucket == "specified_mf":
        return None
    return _add_months(acquired_on, MONTHS[bucket]) + timedelta(days=1)


def grandfathered_cost(actual: float, fmv_2018: float, sale: float) -> float:
    """s.90(7): the higher of actual cost and the lower of the 31 Jan 2018 value and the sale price."""
    return max(actual, min(fmv_2018, sale))


# --- FIFO matching ----------------------------------------------------------------------------

def _fifo(lots: list[dict], sales: list[dict]):
    """Match each sale to the oldest lots of the same ISIN. Returns [(lot, sale, qty)] and what is left per lot id."""
    left = {l["id"]: float(l["quantity"]) for l in lots}
    by_isin: dict[str, list[dict]] = defaultdict(list)
    for lot in sorted(lots, key=lambda l: (l["acquired_on"], l["id"])):
        by_isin[lot["isin"]].append(lot)
    allocs = []
    for sale in sorted(sales, key=lambda s: s["sold_on"]):
        need = float(sale["quantity"])
        for lot in by_isin[sale["isin"]]:
            if need <= 1e-9:
                break
            if lot["acquired_on"] > sale["sold_on"] or left[lot["id"]] <= 1e-9:
                continue
            take = min(need, left[lot["id"]])
            left[lot["id"]] -= take
            need -= take
            allocs.append((lot, sale, take))
        if need > 1e-9:
            raise OversoldError(f"{sale['symbol']} ({sale['isin']}): sold {sale['quantity']:g} on {sale['sold_on']}, "
                                f"but the lots on file are short by {need:g}")
    return allocs, left


def open_lots(lots: list[dict], sales: list[dict]) -> list[dict]:
    _, left = _fifo(lots, sales)
    return [{**l, "quantity": left[l["id"]]} for l in lots if left[l["id"]] > 1e-9]


def _rate(rate_on, day: date, rule: str) -> float:
    when = _month_end_before(day) if rule == "prior_month_end" else day
    rate = rate_on(when) if rate_on else None
    if rate is None:
        raise MissingRate(f"no USD/INR rate on or before {when}")
    return rate


def realise(lots: list[dict], sales: list[dict], fmv_2018: dict | None = None, rate_on=None,
            fx_rule: str = "prior_month_end") -> list[dict]:
    """One row per (lot, sale) pair, in rupees. Foreign money uses `rate_on` on the day the rule picks."""
    fmv_2018 = fmv_2018 or {}
    rows = []
    for lot, sale, qty in _fifo(lots, sales)[0]:
        bucket = bucket_of(lot)
        cost_unit = float(lot["cost_per_unit"])
        grand = False
        if bucket == "equity" and lot["acquired_on"] < GRANDFATHER_DATE and lot["isin"] in fmv_2018:
            cost_unit = grandfathered_cost(cost_unit, float(fmv_2018[lot["isin"]]), float(sale["price_per_unit"]))
            grand = True
        cost_fx = 1.0 if lot.get("currency", "INR") == "INR" else _rate(rate_on, lot["acquired_on"], fx_rule)
        sale_fx = 1.0 if sale.get("currency", "INR") == "INR" else _rate(rate_on, sale["sold_on"], fx_rule)
        cost = qty * cost_unit * cost_fx
        proceeds = qty * float(sale["price_per_unit"]) * sale_fx
        expenses = float(sale.get("expenses") or 0) * qty / float(sale["quantity"]) * sale_fx
        rows.append({"lot_id": lot["id"], "symbol": lot["symbol"], "isin": lot["isin"], "kind": lot.get("kind"),
                     "bucket": bucket, "acquired_on": lot["acquired_on"], "sold_on": sale["sold_on"],
                     "quantity": qty, "cost": cost, "proceeds": proceeds, "expenses": expenses,
                     "gain": proceeds - cost - expenses, "grandfathered": grand,
                     "term": term(bucket, lot["acquired_on"], sale["sold_on"])})
    return rows


# --- netting ----------------------------------------------------------------------------------

def _pool(row: dict) -> str:
    if row["term"] == "short":
        return "stcg_equity" if row["bucket"] == "equity" else "stcg_slab"
    return "ltcg_equity" if row["bucket"] == "equity" else "ltcg_other"


def _absorb(pools: dict, order: tuple, loss: float) -> float:
    for name in order:
        if loss <= 0:
            break
        used = min(loss, max(pools[name], 0))
        pools[name] -= used
        loss -= used
    return loss


def net_gains(rows: list[dict], rules: TaxRules, tax_year: int | None = None, carried: list[dict] | None = None) -> dict:
    """Net a year's rows into the four tax pools. Short-term loss meets short-term gain, then long-term gain;
    long-term loss meets only long-term gain; carried losses come last, oldest first (s.108, 109, 111)."""
    pools = {name: 0.0 for name in SHORT_POOLS + LONG_POOLS}
    for row in rows:
        pools[_pool(row)] += row["gain"]
    stcl = -sum(min(pools[p], 0) for p in SHORT_POOLS)
    ltcl = -sum(min(pools[p], 0) for p in LONG_POOLS)
    for p in SHORT_POOLS + LONG_POOLS:
        pools[p] = max(pools[p], 0)
    stcl = _absorb(pools, SHORT_POOLS + LONG_POOLS, stcl)
    ltcl = _absorb(pools, LONG_POOLS, ltcl)
    items, expired = [], []
    for item in sorted(carried or [], key=lambda i: i["year"]):
        if tax_year is not None and tax_year - item["year"] > CARRY_YEARS:
            expired.append(item)
            continue
        s = _absorb(pools, SHORT_POOLS + LONG_POOLS, item.get("stcl", 0))
        l = _absorb(pools, LONG_POOLS, item.get("ltcl", 0))
        if s or l:
            items.append({"year": item["year"], "stcl": s, "ltcl": l})
    if stcl or ltcl:
        items.append({"year": tax_year, "stcl": stcl, "ltcl": ltcl})
    return {**pools, "expired": expired,
            "carry_forward": {"stcl": sum(i["stcl"] for i in items), "ltcl": sum(i["ltcl"] for i in items),
                              "items": items}}


def inputs(net: dict, slab_income: float = 0) -> dict:
    """The keyword arguments income_tax needs, from a net_gains result."""
    return {"slab_income": slab_income + net["stcg_slab"], "stcg_equity": net["stcg_equity"],
            "ltcg_equity": net["ltcg_equity"], "ltcg_other": net["ltcg_other"]}


# --- tax --------------------------------------------------------------------------------------

def slab_tax(income: float, rules: TaxRules) -> float:
    tax, lower = 0.0, 0.0
    for upper, rate in rules.slabs:
        if income > lower:
            tax += (min(income, upper) - lower) * rate
        lower = upper
    return tax


def _surcharge_rate(total_income: float, rules: TaxRules) -> float:
    for above, rate in rules.surcharge_tiers:
        if total_income > above:
            return rate
    return 0.0


def _core(slab_income, dividend, stcg_equity, ltcg_equity, ltcg_other, rules: TaxRules) -> dict:
    """Tax and surcharge before relief and cess. The surcharge rate follows total income; on dividends and special-rate
    gains it is capped. Marginal relief is applied by the caller."""
    total_income = slab_income + dividend + stcg_equity + ltcg_equity + ltcg_other
    slab = slab_tax(slab_income + dividend, rules)
    salary_slab = slab_tax(slab_income, rules)
    if total_income <= rules.rebate_limit:
        rebate = min(slab, rules.rebate_max)
        slab, salary_slab = slab - rebate, max(salary_slab - rebate, 0)
    else:
        slab = min(slab, total_income - rules.rebate_limit)     # marginal relief; harmless far above the limit
        salary_slab = min(salary_slab, slab)
    special = {"stcg_equity": stcg_equity * rules.stcg_equity_rate,
               "ltcg_equity": max(ltcg_equity - rules.ltcg_exempt, 0) * rules.ltcg_equity_rate,
               "ltcg_other": ltcg_other * rules.ltcg_other_rate}
    rate = _surcharge_rate(total_income, rules)
    capped = min(rate, rules.surcharge_cap_gains)
    surcharge = salary_slab * rate + (slab - salary_slab) * capped + sum(special.values()) * capped
    return {"slab_tax": slab, **special, "surcharge": surcharge, "total_income": total_income}


def _trim(excess: float, parts: list) -> list:
    """Take `excess` rupees of income off the parts in order (salary first, then dividend, then the gains)."""
    out = []
    for value in parts:
        cut = min(value, excess)
        out.append(value - cut)
        excess -= cut
    return out


def income_tax(slab_income: float = 0, stcg_equity: float = 0, ltcg_equity: float = 0, ltcg_other: float = 0,
               *, rules: TaxRules, dividend: float = 0) -> dict:
    """Tax for the year. The rebate (s.156) cuts only slab tax and needs total income at or under Rs 12 lakh; just over it,
    marginal relief caps slab tax at the excess. Surcharge follows the tiers in `rules`, capped at 15% on dividends and
    gains, with marginal relief at the threshold: tax plus surcharge cannot exceed the tax at the threshold plus the
    income above it. For that comparison the income above the threshold comes off salary first, then dividend, then gains."""
    core = _core(slab_income, dividend, stcg_equity, ltcg_equity, ltcg_other, rules)
    surcharge = core["surcharge"]
    base = core["slab_tax"] + core["stcg_equity"] + core["ltcg_equity"] + core["ltcg_other"]
    total_income = core["total_income"]
    threshold = next((above for above, _ in rules.surcharge_tiers if total_income > above), None)
    if threshold is not None:
        slab_t, div_t, other_t, stcg_t, ltcg_t = _trim(total_income - threshold,
                                                       [slab_income, dividend, ltcg_other, stcg_equity, ltcg_equity])
        at = _core(slab_t, div_t, stcg_t, ltcg_t, other_t, rules)
        limit = at["slab_tax"] + at["stcg_equity"] + at["ltcg_equity"] + at["ltcg_other"] + at["surcharge"] \
            + (total_income - threshold)
        surcharge = max(min(surcharge, limit - base), 0)
    before_cess = base + surcharge
    cess = before_cess * rules.cess
    return {"slab_tax": core["slab_tax"], "stcg_equity": core["stcg_equity"], "ltcg_equity": core["ltcg_equity"],
            "ltcg_other": core["ltcg_other"], "surcharge": surcharge, "cess": cess,
            "total": before_cess + cess, "warnings": []}


# --- harvest ----------------------------------------------------------------------------------

def harvest(open_: list[dict], prices: dict, as_of: date, rules: TaxRules, realised_ltcg_equity: float = 0) -> dict:
    """What could be sold today to use the free Rs 1.25 lakh of long-term gain, and which losers could be sold to bank a loss.
    Selling takes the oldest lots first, so a gain is booked from the oldest lot onward and stops at the first lot that is still short-term."""
    room = max(rules.ltcg_exempt - realised_ltcg_equity, 0)
    by_symbol: dict[str, list[dict]] = defaultdict(list)
    for lot in sorted(open_, key=lambda l: (l["acquired_on"], l["id"])):
        if bucket_of(lot) == "equity" and prices.get(lot["symbol"]):
            by_symbol[lot["symbol"]].append(lot)
    candidates, left = [], room
    for symbol, lots in by_symbol.items():
        price = prices[symbol]
        qty = gain = 0.0
        for lot in lots:
            if term("equity", lot["acquired_on"], as_of) != "long" or left <= 0:
                break
            unit = price - lot["cost_per_unit"]
            take = lot["quantity"] if unit <= 0 else min(lot["quantity"], math.floor(left / unit))
            qty, gain, left = qty + take, gain + take * unit, left - take * unit
            if take < lot["quantity"]:
                break
        if qty > 0 and gain > 0:
            candidates.append({"symbol": symbol, "quantity": qty, "gain": gain,
                               "future_tax_saved": gain * rules.ltcg_equity_rate})
    losers = []
    for symbol, lots in by_symbol.items():
        pnl = sum((prices[symbol] - l["cost_per_unit"]) * l["quantity"] for l in lots)
        if pnl < 0:
            losers.append({"symbol": symbol, "quantity": sum(l["quantity"] for l in lots), "loss": -pnl})
    return {"gain_room": room, "gain_candidates": candidates, "gain_room_left": max(left, 0),
            "loss_candidates": sorted(losers, key=lambda c: -c["loss"])}


# --- Schedule FA ------------------------------------------------------------------------------

def schedule_fa(lots: list[dict], sales: list[dict], calendar_year: int, closes: dict, rate_on) -> list[dict]:
    """Foreign shares for the calendar year 1 Jan to 31 Dec: value at purchase, peak, close and sale proceeds, in rupees."""
    start, end = date(calendar_year, 1, 1), date(calendar_year, 12, 31)
    foreign = [l for l in lots if kinds.is_foreign(l)]
    fsales = [s for s in sales if s["isin"] in {l["isin"] for l in foreign}]
    allocs, _ = _fifo(foreign, fsales)

    def rate(day):
        r = rate_on(day)
        if r is None:
            raise MissingRate(f"no USD/INR rate on or before {day}")
        return r

    def units_on(symbol, day):
        bought = sum(l["quantity"] for l in foreign if l["symbol"] == symbol and l["acquired_on"] <= day)
        sold = sum(q for l, s, q in allocs if l["symbol"] == symbol and s["sold_on"] <= day)
        return bought - sold

    rows = []
    for symbol in sorted({l["symbol"] for l in foreign}):
        mine = [l for l in foreign if l["symbol"] == symbol]
        held = [l for l in mine if l["acquired_on"] <= end and (
            l["acquired_on"] >= start or l["quantity"] - sum(
                q for lot, s, q in allocs if lot["id"] == l["id"] and s["sold_on"] < start) > 1e-9)]
        if not held:
            continue
        series = {d: p for d, p in closes.get(symbol, {}).items() if start <= d <= end}
        note = ""
        peak = closing = None
        if series:
            peak = max(units_on(symbol, d) * p * rate(d) for d, p in series.items())
            last = max(series)
            closing = units_on(symbol, end) * series[last] * rate(end)
        else:
            note = "needs price history for this share: peak and closing value left blank"
        rows.append({"symbol": symbol, "isin": mine[0]["isin"], "units_at_close": units_on(symbol, end),
                     "initial_value": sum(l["quantity"] * l["cost_per_unit"] * rate(l["acquired_on"]) for l in held),
                     "peak_value": peak, "closing_value": closing,
                     "gross_proceeds": sum(q * s["price_per_unit"] * rate(s["sold_on"]) for l, s, q in allocs
                                           if l["symbol"] == symbol and start <= s["sold_on"] <= end),
                     "note": note})
    return rows


# --- the ITR pack -----------------------------------------------------------------------------

def _write_csv(path: Path, rows: list[dict], fields: list[str]):
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


README = """Tax pack for FY {label}. Made by stockpilot; give it to whoever files the return.

Files
- summary.json      the year's gains after set-off, and the tax estimate
- schedule_112a.csv long-term equity and equity-fund sales, one line per ISIN and lot (the 112A / s.198 schedule)
- gains_detail.csv  every sale matched to its lot, oldest first
- schedule_fa.csv   foreign shares for calendar year {fy} (Schedule FA)

Form: {form}. ITR-3 instead if any F&O or intraday trading is treated as business income.

Read before relying on it
{warnings}
Gains use the oldest lot first, per ISIN. Compare the totals with Console's tax P&L before filing.
"""


def build_pack(lots: list[dict], sales: list[dict], fy: int, out_dir: Path | str, rate_on, closes: dict,
               fmv_2018: dict | None = None, carried: list[dict] | None = None, slab_income: float = 0,
               fx_rule: str = "prior_month_end", fx_note: str = "") -> dict:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    rules = rules_for(fy)
    start, end = date(fy, 4, 1), date(fy + 1, 3, 31)
    rows = [r for r in realise(lots, sales, fmv_2018, rate_on, fx_rule) if start <= r["sold_on"] <= end]
    net = net_gains(rows, rules, fy, carried)
    estimate = income_tax(**inputs(net, slab_income), rules=rules)
    warnings = list(estimate["warnings"])
    for r in rows:
        if r["bucket"] == "equity" and r["acquired_on"] < GRANDFATHER_DATE and not r["grandfathered"]:
            warnings.append(f"{r['symbol']}: bought before 1 Feb 2018 and no 31 Jan 2018 price on file, so actual cost was used. "
                            "This can overstate the gain.")
    warnings += ["Rules for FY 2026-27 are partly unconfirmed (Finance Act 2026 text, FX-date rule, ITR layouts): see docs/research/tax-rules.md section 11."]
    if fx_note:
        warnings.append(f"USD/INR rates: {fx_note}. Schedule FA wants the SBI TT buying rate; check the figures against it.")
    fa = schedule_fa(lots, sales, fy, closes, rate_on) if any(kinds.is_foreign(l) for l in lots) else []
    _write_csv(out / "gains_detail.csv", rows, ["symbol", "isin", "bucket", "term", "acquired_on", "sold_on", "quantity",
                                                "cost", "proceeds", "expenses", "gain", "grandfathered"])
    _write_csv(out / "schedule_112a.csv", [r for r in rows if r["bucket"] == "equity" and r["term"] == "long"],
               ["isin", "symbol", "acquired_on", "sold_on", "quantity", "proceeds", "cost", "expenses", "gain", "grandfathered"])
    _write_csv(out / "schedule_fa.csv", fa, ["symbol", "isin", "units_at_close", "initial_value", "peak_value",
                                             "closing_value", "gross_proceeds", "note"])
    summary = {"fy": fy_label(fy), "form": "ITR-2", **{k: net[k] for k in (*SHORT_POOLS, *LONG_POOLS)},
               "carry_forward": net["carry_forward"], "expired_losses": net["expired"], "tax": estimate,
               "sales_counted": len(rows), "warnings": warnings}
    (out / "summary.json").write_text(json.dumps(summary, indent=2, default=str))
    (out / "README.txt").write_text(README.format(label=fy_label(fy), fy=fy, form="ITR-2",
                                                  warnings="\n".join(f"- {w}" for w in warnings)))
    return {"itr_form": "ITR-2", "summary": summary, "rows": rows, "net": net, "schedule_fa": fa, "dir": str(out)}
