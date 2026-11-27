"""Fund research: for every Direct/Growth fund in a researched group (fundgroups), a rank inside its group, a plain verdict
and one sentence, from NAVs and costs only. No model, no invented numbers. A past return is one signal, not a promise:
the verdict says "worth considering", never "buy". Nothing here places an order.

Verdict: consider = top quarter of its group over 3 years and it beat the typical fund in most recent quarters; skip =
bottom quarter; fine = the rest; new = under 3 years of prices or too few peers to rank."""
import re
from bisect import bisect_right
from datetime import date, timedelta
from statistics import median

from stockpilot import fundcall, fundgroups
from stockpilot.sources import fundcosts

YEAR = 365
MIN_PEERS = 4
CHECKS = 12                 # quarter-ends looked back for consistency
MIN_CHECKS = 8
CONSIDER_PCT, SKIP_PCT = 0.25, 0.75
CONSISTENT = 0.55
DEAR_TER = 1.5              # a Direct plan costing more than this a year is never "worth considering"
TOLERANCE_DAYS = 10         # a NAV this many days older than the day asked for still counts (weekends, holidays)
IDEAS_PER_GROUP = 3
CAVEAT = ("Only funds still open today are on file, so funds that closed or merged are missing and every rank is a little "
          "flattering. A good past record does not promise a good future.")
_NAME_NOISE = re.compile(r"\s*-?\s*\b(direct|regular|growth|plan|option)\b", re.I)


def _ord(n: int) -> str:
    return f"{n}{'th' if 10 <= n % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')}"


def _series(db, codes: list[int]) -> dict[int, tuple[list, list]]:
    out: dict[int, tuple[list, list]] = {}
    cur = db.execute("select scheme_code, date, nav from navs where list_contains(?, scheme_code) and nav > 0 "
                     "order by scheme_code, date", [codes])
    while rows := cur.fetchmany(50000):
        for code, day, nav in rows:
            d, n = out.setdefault(code, ([], []))
            d.append(day)
            n.append(nav)
    return out


def _at(s, day: date):
    dates, navs = s
    i = bisect_right(dates, day) - 1
    return navs[i] if i >= 0 and (day - dates[i]).days <= TOLERANCE_DAYS else None


def _cagr(now, then, years):
    return (now / then) ** (1 / years) - 1 if now and then else None


def _worst_fall(s, as_of: date, years: int = 3):
    dates, navs = s
    lo = bisect_right(dates, as_of - timedelta(days=years * YEAR))
    peak, worst = 0.0, 0.0
    for v in navs[lo:bisect_right(dates, as_of)]:
        peak = max(peak, v)
        if peak:
            worst = max(worst, 1 - v / peak)
    return worst if peak else None


def _metrics(s, as_of: date) -> dict | None:
    now = _at(s, as_of)
    if now is None:
        return None
    first = s[0][0]
    years = (as_of - first).days / YEAR
    return {"nav": now, "nav_date": s[0][bisect_right(s[0], as_of) - 1], "years": years,
            "ret_1y": _cagr(now, _at(s, as_of - timedelta(days=YEAR)), 1),
            "ret_3y": _cagr(now, _at(s, as_of - timedelta(days=3 * YEAR)), 3) if years >= 3 else None,
            "ret_5y": _cagr(now, _at(s, as_of - timedelta(days=5 * YEAR)), 5) if years >= 5 else None,
            "worst_fall": _worst_fall(s, as_of) if years >= 3 else None}


def _clean(name: str) -> str:
    return " ".join(_NAME_NOISE.sub("", name or "").replace(" - ", " ").split()).strip(" -")


def research(db, as_of: date, held=(), watching=()) -> dict:
    held, watching = set(held), set(watching)
    rows = [r for r in db.execute("select scheme_code, isin_growth, name, category, house from funds "
                                  "where plan like 'Direct%' and option like '%Growth%'").fetchall()
            if fundgroups.group_of(r[3], r[2])]
    series = _series(db, [r[0] for r in rows])
    groups: dict[str, list[dict]] = {}
    for code, isin, name, category, house in rows:
        s = series.get(code)
        m = s and _metrics(s, as_of)
        if not m:
            continue
        costs = fundcosts.lookup(db, name, "Direct")
        groups.setdefault(fundgroups.group_of(category, name), []).append(
            {"code": code, "isin": isin, "name": _clean(name), "house": house, "category": category, **m, "ter": costs and costs["ter"],
             "aum_cr": costs and costs["aum_cr"], "held": isin in held, "watching": isin in watching, "_s": s})
    rates = {(g, q): (n, hit, periods) for g, q, n, hit, periods in db.execute(
        "select group_name, quartile, n, hit_rate, periods from fund_base_rates where horizon_days = ?", [fundcall.HORIZON_DAYS]).fetchall()}
    out_groups = []
    for label in fundgroups.ORDER:
        funds = groups.get(label)
        if not funds:
            continue
        rankable = sorted((f for f in funds if f["ret_3y"] is not None), key=lambda f: -f["ret_3y"])
        n, med = len(rankable), median(f["ret_3y"] for f in rankable) if rankable else None
        checks = _checkpoints(funds, as_of)
        for i, f in enumerate(rankable, 1):
            f["rank"] = [i, n]
        for f in funds:
            f.setdefault("rank", None)
            f["consistency"] = checks.get(f["code"])
            _judge(f, label, n, med)
            f["reasoning"] = _reasoning(f, label, n, med, rates)
            f["spark"] = _spark(f["_s"], as_of)
            f.pop("_s", None)
        funds.sort(key=lambda f: (f["rank"] is None, f["rank"][0] if f["rank"] else 0, -(f["ret_1y"] or 0)))
        out_groups.append({"name": label, "n": n, "median_3y": med, "funds": funds})
    ideas = []
    for g in out_groups:
        picks = [f for f in g["funds"] if f["verdict"] == "consider" and not f["held"]][:IDEAS_PER_GROUP]
        ideas += [{**f, "group": g["name"]} for f in picks]
    for g in out_groups:
        for f in g["funds"]:
            f["group"] = g["name"]
    return {"as_of": str(as_of), "caveat": CAVEAT, "groups": out_groups, "ideas": ideas}


def _spark(s, as_of: date, months: int = 36) -> list[float]:
    """One NAV a month for three years, oldest first, for the small chart. A month with no price is left out."""
    pts = [_at(s, as_of - timedelta(days=30 * k)) for k in range(months, -1, -1)]
    return [round(v, 4) for v in pts if v is not None]


def _checkpoints(funds: list[dict], as_of: date) -> dict[int, list]:
    """{code: [quarters it beat the group's typical fund over the year ending then, quarters checked]}."""
    days = [as_of - timedelta(days=91 * i) for i in range(CHECKS)]
    per_day = []
    for q in days:
        r = {f["code"]: _cagr(_at(f["_s"], q), _at(f["_s"], q - timedelta(days=YEAR)), 1) for f in funds}
        r = {c: v for c, v in r.items() if v is not None}
        per_day.append((r, median(r.values()) if len(r) >= MIN_PEERS else None))
    out = {}
    for f in funds:
        got = [(r[f["code"]] >= med) for r, med in per_day if med is not None and f["code"] in r]
        if len(got) >= MIN_CHECKS:
            out[f["code"]] = [sum(got), len(got)]
    return out


def _crore(x: float) -> str:
    return f"₹{x:,.0f} crore"


def _judge(f: dict, group: str, n: int, med) -> None:
    f["small"] = bool(f["aum_cr"] is not None and f["aum_cr"] < fundcosts.SMALL_AUM_CR)
    parts = []
    if f["ret_3y"] is None or f["rank"] is None or n < MIN_PEERS:
        f["verdict"] = "new"
        parts.append("It has less than 3 years of prices, so it is not ranked yet." if f["ret_3y"] is None
                     else f"Only {n} comparable funds in {group}, too few to rank.")
        if f["ret_1y"] is not None:
            parts.append(f"Last year it returned {f['ret_1y']:.1%}.")
    else:
        pct = (f["rank"][0] - 1) / (n - 1) if n > 1 else 0.0
        done, total = f["consistency"] or (None, None)
        steady = done is None or done / total >= CONSISTENT
        dear = f["ter"] is not None and f["ter"] > DEAR_TER
        f["verdict"] = "consider" if pct <= CONSIDER_PCT and steady and not dear and not f["small"] else "skip" if pct > SKIP_PCT else "fine"
        parts.append(f"{_ord(f['rank'][0])} of {f['rank'][1]} in {group} over 3 years: {f['ret_3y']:.1%} a year, the typical fund "
                     f"{med:.1%}.")
        if total:
            parts.append(f"It beat the typical fund in {done} of the last {total} quarters.")
        if f["worst_fall"] is not None:
            parts.append(f"Its worst fall in 3 years was {f['worst_fall']:.0%}.")
    if f["ter"] is not None:
        parts.append(f"Costs {f['ter']:.2f}% a year" + (", which is dear for a fund like this." if f["ter"] > DEAR_TER else "."))
    if f["small"]:
        parts.append(f"Small fund: about {_crore(f['aum_cr'])} of assets, under ₹{fundcosts.SMALL_AUM_CR} crore, so it is never worth considering.")
    f["why"] = " ".join(parts)


# ---- the `reasoning` object for a fund (contract: docs/build-lanes-v11.md) --------------------------------------------

STANCE_OF_VERDICT = {"consider": "buy", "fine": "hold", "skip": "weak", "new": "none"}
STANCE_OF_CALL = {"Keep": "hold", "Add": "buy", "Stop adding": "watch", "Switch": "sell", "Review": "weak"}
HEADLINE = {"consider": "Worth considering", "fine": "Nothing special", "skip": "Weak against its peers", "new": "Too new to judge"}


def _item(text, area, weight=None):
    return {"text": text, "weight": weight, "area": area, "by": "code"}


def _reasoning(f: dict, group: str, n: int, med, rates: dict) -> dict:
    """Plain reasons from the fund's own numbers. The chance is the measured rate for its rank quartile (fund_base_rates),
    and absent when fewer than 30 cases back it. Every number in a sentence is a field of the fund (or the rate row)."""
    r = {"v": 1, "horizon": "about 12 months", "stance": STANCE_OF_VERDICT[f["verdict"]]}
    up, down, facts = [], [], []
    rate = None
    if f["rank"] and n >= MIN_PEERS:
        quartile = -(-4 * f["rank"][0] // f["rank"][1])
        row = rates.get((fundcall.group_of(f.get("category")), quartile))
        if row and row[0] >= fundcall.MIN_N and row[2] >= fundcall.MIN_PERIODS:
            rate = {"p": round(row[1], 4), "n": row[0]}
        weight = round((rate["p"] - 0.5) * 100, 1) if rate else None
        text = (f"Ranked {_ord(f['rank'][0])} of {f['rank'][1]} in {group} over three years: {f['ret_3y']:.1%} a year, "
                f"the typical fund {med:.1%}")
        (up if (weight if weight is not None else (0.5 - f["rank"][0] / f["rank"][1])) >= 0 else down).append(_item(text, "trend", weight))
    done, total = f["consistency"] or (None, None)
    if total:
        (up if done / total >= CONSISTENT else down).append(
            _item(f"Beat the typical fund in {done} of the last {total} quarters", "trend"))
    if f["small"]:
        down.append(_item(f"Small fund: about {_crore(f['aum_cr'])} of assets, so it can be merged or closed", "size"))
    if f["ter"] is not None:
        if f["ter"] > DEAR_TER:
            down.append(_item(f"Costs {f['ter']:.2f}% a year, which is dear for a fund like this", "value"))
        else:
            facts.append({"text": f"Costs {f['ter']:.2f}% a year", "area": "value"})
    if f["worst_fall"] is not None:
        facts.append({"text": f"Its worst fall in three years was {f['worst_fall']:.0%}", "area": "risk"})
    if f["ret_1y"] is not None:
        facts.append({"text": f"Last year it returned {f['ret_1y']:.1%}", "area": "trend"})
    key = lambda i: -abs(i["weight"] or 0)
    r["for"], r["against"], r["facts"] = sorted(up, key=key)[:5], sorted(down, key=key)[:5], facts
    if f["rank"] and n >= MIN_PEERS:
        r["headline"] = f"{HEADLINE[f['verdict']]}: ranks {_ord(f['rank'][0])} of {f['rank'][1]} in {group}."
    else:
        r["headline"] = f"{HEADLINE[f['verdict']]}: not enough price history to rank it."
    if rate:
        r["chance"] = {"p": rate["p"], "base_rate": 0.5, "n": rate["n"], "hurdle_pct": 0,
                       "explain": (f"Out of 100 funds ranked like this, {round(100 * rate['p'])} stayed above the typical fund "
                                   f"over the next year ({rate['n']} cases measured). A fund picked at random would manage half.")}
    r["change_view"] = _change_view(f)
    return r


def _change_view(f: dict) -> list[dict]:
    if f["verdict"] == "consider":
        return [{"text": "Slipping out of the top quarter of its group, or a cost turning dear, would take it off the list", "turns": "hold"}]
    if f["verdict"] in ("fine", "skip") and not f["small"]:
        return [{"text": "Climbing into the top quarter of its group and staying steady would make it worth considering", "turns": "buy"}]
    return []


def attach_calls(research_doc: dict, calls: list[dict]) -> None:
    """Put the weekly call and the SIP of each held fund on its row, and let the call set the stance and headline."""
    by = {c["isin"]: c for c in calls if c.get("isin")}
    for g in research_doc["groups"]:
        for f in g["funds"]:
            c = by.get(f["isin"])
            if not c:
                continue
            f["call"], f["call_line"], f["sip"] = c["call"], c.get("line"), c.get("sip")
            r = f["reasoning"]
            r["stance"] = STANCE_OF_CALL.get(c["call"], r["stance"])
            r["headline"] = f"{c['call']}: " + r["headline"][0].lower() + r["headline"][1:]
            sip = c.get("sip")
            if sip and sip.get("next"):
                d = date.fromisoformat(sip["next"])
                r["facts"] = r["facts"] + [{"text": f"Your SIP of ₹{sip['amount']:,.0f} goes out next on {d.day} {d:%b}", "area": "size"}]
