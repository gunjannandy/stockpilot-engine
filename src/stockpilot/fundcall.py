"""The weekly fund forecaster (R13, docs/adr/0007-fund-forecaster.md): one call per held fund (Keep, Add, Stop adding,
Switch, Review). Order: measure the base rate on the NAVs we hold -> code screen -> one model call on the shortlist ->
the two views are combined (neither rubber-stamps the other) -> code sizing and the plain-English line -> stored,
scored later against the category's middle fund. Nothing here places an order: it reads NAVs and trades, and writes
only `fund_calls`, `fund_base_rates` and the `fund_calls` weekly report.

Every number in a line comes from code. The model supplies a chance, a stance and one sentence with no digits."""
import json
import math
import re
from datetime import date, timedelta
from statistics import median

from stockpilot import costs, valuation

from stockpilot.sources import fundcosts

from stockpilot.analysis import fundreview, tax

from stockpilot.calls import record, runner
from stockpilot.book import positions

HORIZON_DAYS = 365
STEP_MONTHS = 3                    # checkpoints are quarter-spaced; monthly ones would overlap even more
MIN_N, MIN_PERIODS = 30, 4         # below either, no base rate is given
ADD_PCT, STOP_PCT, REVIEW_PCT = 0.25, 0.50, 0.75      # 3-year rank as a share of the category: top quarter, half, bottom quarter
ADD_CONSISTENCY, WEAK_CONSISTENCY = 0.60, 0.50
SWITCH_COST_MAX = 0.02             # tax plus known exit load above 2% of the holding: Review, not Switch
TAX_WAIT_DAYS = 60
DIRECT_GAP_POINTS = 0.5            # a Regular plan this much dearer a year than its Direct twin: Switch to the twin
ADD_MIN_CHANCE, SWITCH_MAX_CHANCE, ESCALATE_CHANCE, KEEP_CHANCE = 0.55, 0.45, 0.35, 0.60
MODEL_MOVE_MAX = 0.25              # code keeps the model within this of the base rate
SIP_MONTHS, SIP_TOLERANCE = 4, 0.10
LOAD_DAYS = 365
CALLS = ("Keep", "Add", "Stop adding", "Switch", "Review")
STANCES = {"keep": "Keep", "add": "Add", "stop_adding": "Stop adding", "switch": "Switch", "review": "Review"}
CAVEAT = ("Only funds still alive today are on file, so funds that closed or merged are missing and every rate is a little "
          "flattering. Checks overlap, so the cases count overstates the evidence.")


# ---- the base rate, measured --------------------------------------------------------------------------

def group_of(category: str | None) -> str:
    return (category or "Other").split(" - ")[0].strip()


def _month(day: date) -> int:
    return day.year * 12 + day.month - 1


def _grid(db, codes: list[int], as_of: date) -> dict[int, dict[int, float]]:
    """The last NAV in each month, per fund: {code: {month number: nav}}."""
    out: dict[int, dict[int, float]] = {}
    for code, day, nav in db.execute(
            "select scheme_code, date, nav from navs where list_contains(?, scheme_code) and date <= ? and nav > 0 "
            "qualify row_number() over (partition by scheme_code, date_trunc('month', date) order by date desc) = 1",
            [codes, as_of]).fetchall():
        out.setdefault(code, {})[_month(day)] = nav
    return out


def _peer_codes(db) -> dict[str, list[int]]:
    cats: dict[str, list[int]] = {}
    for code, category in db.execute("select scheme_code, category from funds where plan like 'Direct%' "
                                     "and option like '%Growth%' and category is not null").fetchall():
        cats.setdefault(category, []).append(code)
    return cats


def base_rates(db, as_of: date) -> dict[tuple[str, int], dict]:
    """{(group, quartile): n, periods, hit_rate, avg_excess, cost_drag}: at each quarter-end checkpoint with 3 years of NAVs
    behind and 12 months ahead, funds are ranked on 3-year return inside their category; a hit is beating that category's
    middle fund over the next 12 months."""
    tally: dict[tuple[str, int], dict] = {}
    last = _month(as_of)
    for category, codes in _peer_codes(db).items():
        grid = _grid(db, codes, as_of)
        if not grid:
            continue
        first = min(min(g) for g in grid.values())
        group = group_of(category)
        t = last - 12
        while t - 36 >= first:
            r3 = {c: (g[t] / g[t - 36]) ** (1 / 3) - 1 for c, g in grid.items() if t in g and t - 36 in g}
            ahead = {c: g[t + 12] / g[t] - 1 for c, g in grid.items() if t in g and t + 12 in g}
            both = [c for c in r3 if c in ahead]
            if len(both) >= fundreview.MIN_PEERS:
                middle = median(ahead[c] for c in both)
                n = len(both)
                for rank, c in enumerate(sorted(both, key=lambda c: -r3[c]), start=1):
                    q = tally.setdefault((group, math.ceil(4 * rank / n)),
                                         {"n": 0, "hits": 0, "excess": 0.0, "periods": set(), "codes": set()})
                    q["n"] += 1
                    q["hits"] += ahead[c] > middle
                    q["excess"] += ahead[c] - middle
                    q["periods"].add(t)
                    q["codes"].add(c)
            t -= STEP_MONTHS
    ters = {}
    out = {}
    for key, q in tally.items():
        drags = []
        for code in q["codes"]:
            if code not in ters:
                row = db.execute("select name from funds where scheme_code = ?", [code]).fetchone()
                found = row and fundcosts.lookup(db, row[0], "Direct")
                ters[code] = found["ter"] if found else None
            if ters[code] is not None:
                drags.append(ters[code])
        out[key] = {"n": q["n"], "periods": len(q["periods"]), "hit_rate": q["hits"] / q["n"],
                    "avg_excess": q["excess"] / q["n"], "cost_drag": sum(drags) / len(drags) if drags else None}
    return out


def save_base_rates(db, rates: dict, computed_on: date) -> None:
    db.execute("delete from fund_base_rates where horizon_days = ?", [HORIZON_DAYS])
    for (group, quartile), r in rates.items():
        db.execute("insert into fund_base_rates values (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                   [HORIZON_DAYS, group, quartile, r["n"], r["periods"], r["hit_rate"], r["avg_excess"], r["cost_drag"], computed_on])


def rate_for(db, category: str | None, rank: tuple[int, int]) -> tuple[dict | None, str]:
    """(the stored rate for a fund's group and quartile, why there is none). Never a made-up rate."""
    quartile = math.ceil(4 * rank[0] / rank[1])
    row = db.execute("select n, periods, hit_rate, avg_excess, cost_drag from fund_base_rates "
                     "where horizon_days = ? and group_name = ? and quartile = ?", [HORIZON_DAYS, group_of(category), quartile]).fetchone()
    n = row[0] if row else 0
    if not row or row[0] < MIN_N or row[1] < MIN_PERIODS:
        return None, (f"Not enough price history on file to say how often funds like this stay on top (only {n} cases); "
                      "no rate is given.")
    return {"rate": row[2], "n": row[0], "periods": row[1], "avg_excess": row[3], "cost_drag": row[4]}, ""


# ---- what each held fund looks like -------------------------------------------------------------------

def _quarterly_checks(db, code: int, peers: list[int], as_of: date) -> tuple[int, int]:
    """(quarters at or above the category's middle fund on 1-year return, quarters checked), the last 12 quarters."""
    grid = _grid(db, peers + [code], as_of)
    last, hit, total = _month(as_of), 0, 0
    for t in range(last, last - 3 * 12, -STEP_MONTHS):
        ret = {c: g[t] / g[t - 12] - 1 for c, g in grid.items() if t in g and t - 12 in g}
        if code not in ret or len(ret) < fundreview.MIN_PEERS:
            continue
        total += 1
        hit += ret[code] >= median(ret.values())
    return hit, total


def sip_schedule(db, isin: str | None, as_of: date) -> dict | None:
    """A monthly buy pattern read from the trades table (Coin mails, Kite): 3 or more months of the last 4 with a buy, the
    amounts within 10% of their median. None when there is no pattern: then no amount is ever suggested."""
    if not isin:
        return None
    since = as_of - timedelta(days=31 * SIP_MONTHS)
    rows = db.execute("select trade_date, quantity * price from trades where isin = ? and side = 'buy' and kind in ('mf', 'fund') "
                      "and trade_date > ? and trade_date <= ? and quantity > 0 and price > 0", [isin, since, as_of]).fetchall()
    by_month: dict[int, tuple] = {}
    for day, amount in rows:
        by_month[_month(day)] = (day, amount)
    if len(by_month) < 3:
        return None
    amounts = [a for _, a in by_month.values()]
    mid = median(amounts)
    if any(abs(a - mid) > SIP_TOLERANCE * mid for a in amounts):
        return None
    sip = {"amount": round(mid), "day": int(median(d.day for d, _ in by_month.values())), "months": len(by_month)}
    sip["next"] = str(next_sip(sip, as_of))
    return sip


def next_sip(sip: dict | None, as_of: date) -> date | None:
    """The next SIP date on or after `as_of`; a day the month lacks (the 31st) falls on the month's last day."""
    if not sip:
        return None
    y, m = as_of.year, as_of.month
    for _ in range(2):
        last = ((date(y + m // 12, m % 12 + 1, 1)) - timedelta(days=1)).day
        d = date(y, m, min(sip["day"], last))
        if d >= as_of:
            return d
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return d


def _inr(x: float) -> str:
    x = abs(x)
    if x >= 1e7:
        return f"₹{x / 1e7:.1f} crore".replace(".0 ", " ")
    if x >= 1e5:
        return f"₹{x / 1e5:.1f} lakh".replace(".0 ", " ")
    return f"₹{x:,.0f}"


def _target_for(rows_peers: dict, small: set) -> dict | None:
    """The same-category Direct/Growth fund a switch would go to: the best 3-year return in the top quarter that is not small."""
    ordered = sorted(rows_peers.items(), key=lambda kv: -kv[1]["ret_3y"])
    n = len(ordered) + 1
    for name, p in ordered[:max(1, n // 4)]:
        if name not in small and p["aum_cr"] is not None:
            return {"name": name, "code": p["code"], "ret_3y": p["ret_3y"], "ter": p["ter"], "kind": "peer"}
    return None


def _direct_twin(db, name: str, category: str) -> dict | None:
    key = fundcosts.scheme_key(name)
    for code, pname in db.execute("select scheme_code, name from funds where plan like 'Direct%' and option like '%Growth%' "
                                  "and category = ?", [category]).fetchall():
        if fundcosts.scheme_key(pname) == key:
            found = fundcosts.lookup(db, pname, "Direct")
            return {"name": pname, "code": code, "ret_3y": None, "ter": found and found["ter"], "kind": "direct_twin"}
    return None


def _consistency_text(hit: int, total: int) -> str:
    return f"At or above the category's middle fund in {hit} of the last {total} quarterly checks."


def facts(db, as_of: date, exit_loads: dict | None = None) -> list[dict]:
    """One row per held fund: the fund's facts (these go to the model), the holding's own numbers (these never do) and
    the code screen's call."""
    review = {r["isin"]: r for r in fundreview.review(db, as_of)}
    out = []
    for p in positions.held(db, as_of):
        if p.kind != "mf":
            continue
        base = review.get(p.isin)
        fund = valuation.fund_for(db, p.isin)
        row = {"id": None, "isin": p.isin, "name": base["name"] if base else p.name, "category": base and base.get("category"),
               "judged": False, "value": p.quantity * (p.price or 0), "price": p.price, "lots": p.lots,
               "ter": base and base.get("ter"), "aum_cr": base and base.get("aum_cr"), "small": bool(base and base["flags"]),
               "ret_3y": base and base.get("ret_3y"), "ret_1y": base and base.get("ret_1y"), "rank": base and base.get("rank"),
               "median_3y": base and base.get("median_3y"), "code": fund and fund[0], "plan": fund and fund[2],
               "base_rate": None, "base_rate_note": "", "consistency": None, "checks": (0, 0), "target": None,
               "sip": sip_schedule(db, p.isin, as_of), "note": base.get("note", "") if base else ""}
        if not base or not base["rank"]:
            row["why_unjudged"] = base["why"] if base else "This fund is not in the AMFI list, so it cannot be compared."
            out.append(row)
            continue
        row["judged"] = True
        rank, n = base["rank"]
        row["pct"] = rank / n
        row["base_rate"], row["base_rate_note"] = rate_for(db, row["category"], base["rank"])
        peers, small = {}, set()
        for pcode, pname in db.execute("select scheme_code, name from funds where category = ? and plan like 'Direct%' and "
                                       "option like '%Growth%' and scheme_code <> ?", [row["category"], fund[0]]).fetchall():
            r3 = fundreview._returns(db, pcode, as_of)["ret_3y"]
            c = fundcosts.lookup(db, pname, "Direct")
            if r3 is not None:
                peers[pname] = {"code": pcode, "ret_3y": r3, "ter": c and c["ter"], "aum_cr": c and c["aum_cr"]}
                if fundcosts.is_small(c):
                    small.add(pname)
        hit, total = _quarterly_checks(db, fund[0], [v["code"] for v in peers.values()], as_of)
        row["checks"], row["consistency"] = (hit, total), (hit / total if total >= MIN_PERIODS else None)
        row["peer_target"] = _target_for(peers, small)
        row["twin"] = _direct_twin(db, row["name"], row["category"]) if (row["plan"] or "").lower().startswith("regular") else None
        row["exit_load_pct"] = (exit_loads or {}).get(p.isin)
        out.append(row)
    for i, row in enumerate(out, start=1):
        row["id"] = f"F{i}"
    return out


# ---- the switch: its price, in tax, exit load and yearly cost --------------------------------------------

def switch_cost(row: dict, target: dict, as_of: date) -> dict:
    """What moving the whole holding to `target` costs and saves, all computed here. `ok` is False with `why` when the call
    cannot honestly be a Switch."""
    lots = [{"acquired_on": l.acquired_on, "quantity": l.quantity, "cost": l.cost, "turns_long_term_on": l.turns_long_term_on}
            for l in row["lots"]]
    value = row["value"]
    out = {"target": target["name"], "kind": target["kind"], "ok": False, "why": "", "tax": None, "load": None,
           "saved_points": None, "saved_inr": None}
    buckets = {tax.mf_bucket(row["category"], l["acquired_on"], row["name"]) for l in lots}
    if not lots or not row["price"]:
        out["why"] = "No purchase lots are on file, so the tax on switching cannot be worked out."
        return out
    if buckets != {"equity"}:
        out["why"] = "This is not an equity fund: tax on switching depends on your income slab and is not worked out here."
        return out
    t = costs.tax_if_sold(lots, row["price"], as_of)
    out["tax"], out["short_gain"], out["long_gain"] = t["tax"], t["short_gain"], t["long_gain"]
    young = sum(l["quantity"] * row["price"] for l in lots if (as_of - l["acquired_on"]).days < LOAD_DAYS)
    out["young_value"] = young
    pct = row.get("exit_load_pct")
    out["load"] = None if pct is None else young * pct / 100
    out["load_pct"] = pct
    own, theirs = row["ter"], target["ter"]
    if own is None or theirs is None:
        out["why"] = "The yearly cost of one of the two funds is not on file, so the saving cannot be shown."
        return out
    out["saved_points"] = own - theirs
    out["saved_inr"] = value * (own - theirs) / 100
    soon = [l["turns_long_term_on"] for l in lots if l["turns_long_term_on"] and as_of < l["turns_long_term_on"]
            <= as_of + timedelta(days=TAX_WAIT_DAYS)]
    if soon and t["short_gain"] > 0:
        out["why"] = (f"Some units turn long-term on {min(soon).day} {min(soon):%b %Y}; waiting cuts the tax. "
                      f"Switching today would cost about {_inr(t['tax'])} in tax.")
        return out
    total = t["tax"] + (out["load"] or 0)
    if value and total > SWITCH_COST_MAX * value:
        out["why"] = (f"Switching now would cost about {_inr(total)} in tax and exit load, more than "
                      f"{SWITCH_COST_MAX:.0%} of the holding ({_inr(value)}).")
        return out
    out["ok"] = True
    return out


def switch_text(c: dict) -> str:
    gains = []
    if c.get("long_gain"):
        gains.append(f"long-term gain {_inr(c['long_gain'])}")
    if c.get("short_gain"):
        gains.append(f"short-term gain {_inr(c['short_gain'])}")
    shape = f" ({', '.join(gains)})" if gains else ""
    tax_part = f"about {_inr(c['tax'])} in tax{shape}" if c["tax"] else "no tax to pay"
    if c["load"] is not None:
        load = f"exit load about {_inr(c['load'])}"
    else:
        load = (f"exit load not on file; units under a year old ({_inr(c['young_value'])}) may carry one"
                if c.get("young_value") else "no units under a year old, so usually no exit load")
    pts = c["saved_points"]
    saving = (f"It saves about {_inr(c['saved_inr'])} a year in fund charges ({pts:.2f} points less)." if pts > 0
              else f"It costs about {_inr(-c['saved_inr'])} a year more in fund charges ({-pts:.2f} points more).")
    return f"Switching to {c['target']} costs {tax_part} and {load}. {saving}"


# ---- the code screen, then the model, then the combined call ---------------------------------------------

def screen(db, row: dict, as_of: date) -> dict:
    """The code's call and its own reason. Switch needs the line to carry both costs, else it becomes Review."""
    if not row["judged"]:
        return {"call": "Keep", "why": row["why_unjudged"], "switch": None}
    pct, cons = row["pct"], row["consistency"]
    switch, call = None, "Keep"
    target = None
    twin = row.get("twin")
    if twin and row["ter"] is not None and twin["ter"] is not None and row["ter"] - twin["ter"] >= DIRECT_GAP_POINTS:
        call, target = "Switch", twin
    elif pct > REVIEW_PCT:
        call = "Review"
        if cons is not None and cons < WEAK_CONSISTENCY and row["peer_target"]:
            call, target = "Switch", row["peer_target"]
    elif pct > STOP_PCT or row["small"]:
        call = "Stop adding"
    elif pct <= ADD_PCT and cons is not None and cons >= ADD_CONSISTENCY:
        call = "Add"
    why = {"Keep": "Nothing in the screen asks for a change.",
           "Add": "Top quarter of its category over 3 years and steady quarter by quarter.",
           "Stop adding": "Small fund, or in the lower half of its category over 3 years." if not row["small"] or pct > STOP_PCT
           else "A small fund that can be merged or closed.",
           "Review": "Bottom quarter of its category over 3 years.",
           "Switch": "Dearer than its own Direct plan." if target and target["kind"] == "direct_twin"
           else "Bottom quarter of its category and rarely at the middle lately."}[call]
    if call == "Switch":
        switch = switch_cost(row, target, as_of)
        if not switch["ok"]:
            call, why = "Review", why + " " + switch["why"]
    return {"call": call, "why": why, "switch": switch}


def _clamp_chance(p, base):
    if p is None:
        return None
    p = min(0.98, max(0.02, float(p)))
    if base is not None:
        p = min(base + MODEL_MOVE_MAX, max(base - MODEL_MOVE_MAX, p))
    return round(p, 4)


def combine(code_call: str, model: dict | None, has_rate: bool) -> tuple[str, str]:
    """(final call, what changed). The model may veto a money-moving call or raise a Keep to Review; it never creates an
    Add or a Switch. With no model answer, nothing moves money on code alone."""
    if model is None:
        if code_call == "Add":
            return "Keep", "The model did not weigh in, so nothing is added on the screen alone."
        if code_call == "Switch":
            return "Review", "The model did not weigh in, so nothing is switched on the screen alone."
        return code_call, ""
    p, stance = model["probability"] if has_rate else None, model["stance"]
    if code_call == "Add":
        if stance not in ("add", "keep") or (p is not None and p < ADD_MIN_CHANCE):
            return "Keep", "The model did not back adding more."
    elif code_call == "Switch":
        if stance not in ("switch", "review", "stop_adding") or (p is not None and p > SWITCH_MAX_CHANCE):
            return "Review", "The model did not back switching."
    elif code_call == "Stop adding":
        if stance == "keep" and p is not None and p >= KEEP_CHANCE:
            return "Keep", "The model sees no reason to stop adding."
    elif code_call == "Keep":
        if stance in ("review", "switch", "stop_adding") and p is not None and p <= ESCALATE_CHANCE:
            return "Review", "The model sees a weak year ahead for it."
    return code_call, ""


def shortlist(rows: list[dict], screened: dict) -> list[dict]:
    return [r for r in rows if r["judged"] and (screened[r["id"]]["call"] != "Keep"
                                                 or (r["consistency"] is not None and r["consistency"] < WEAK_CONSISTENCY))]


def brief_for(rows: list[dict], screened: dict) -> dict:
    """Fund facts only: no units, values, costs, lots, SIPs or tax (a test holds this to it)."""
    funds = []
    for r in rows:
        s = screened[r["id"]]
        sw = s["switch"]
        alt = None if not sw else (r["twin"] if sw["kind"] == "direct_twin" else r["peer_target"])
        funds.append({"id": r["id"], "name": r["name"], "category": r["category"], "rank": list(r["rank"]),
                      "ret_3y": r["ret_3y"], "ret_1y": r["ret_1y"], "consistency": r["consistency"], "ter": r["ter"],
                      "aum_cr": r["aum_cr"], "small": r["small"],
                      "base_rate": r["base_rate"] and {"rate": r["base_rate"]["rate"], "n": r["base_rate"]["n"],
                                                       "avg_cost_pct": r["base_rate"]["cost_drag"]},
                      "code_call": s["call"], "code_why": s["why"],
                      "alternative": alt and {"name": alt["name"], "ret_3y": alt["ret_3y"], "ter": alt["ter"]}})
    return {"horizon_months": 12, "funds": funds}


def _plain(text: str | None) -> str:
    text = " ".join((text or "").split())
    return "" if re.search(r"\d", text) or runner.jargon_in(text) else text


def _sizing(call: str, row: dict, sw: dict | None) -> str:
    sip = row["sip"]
    if call == "Add":
        return (f"Keep your SIP of {_inr(sip['amount'])} a month (about the {sip['day']}th) going." if sip
                else "No SIP is on file for it, so no amount is suggested; add when you next have money to invest.")
    if call == "Stop adding":
        return (f"Pause the {_inr(sip['amount'])} monthly SIP; keep what you hold." if sip
                else "Do not add more; keep what you hold.")
    if call == "Switch" and sip and sw:
        return f"Move the {_inr(sip['amount'])} monthly SIP to {sw['target']} as well."
    return ""


def line_for(row: dict, call: str, screen_: dict, change: str, reason: str) -> str:
    parts = []
    if row["judged"]:
        rank, n = row["rank"]
        parts.append(f"{rank} of {n} in {row['category']} over 3 years ({row['ret_3y']:.1%} a year, the middle fund made "
                     f"{row['median_3y']:.1%}).")
        if row["consistency"] is not None:
            parts.append(_consistency_text(*row["checks"]))
        br = row["base_rate"]
        parts.append(f"Funds in this position stayed above the middle {br['rate']:.0%} of the time over the next year "
                     f"({br['n']} cases)." if br else row["base_rate_note"])
    else:
        parts.append("Too early to judge. " + row["why_unjudged"])
    sw = screen_.get("switch")
    if call == "Switch" and sw and sw["ok"]:
        parts.append(switch_text(sw))
    elif sw and not sw["ok"]:
        parts.append(sw["why"])
    if row["small"]:
        parts.append(f"Small fund: about {_inr(row['aum_cr'] * 1e7)} of assets.")
    if row["note"]:
        parts.append(row["note"])
    if change:
        parts.append(change)
    if reason:
        parts.append(reason)
    size = _sizing(call, row, sw if call == "Switch" else None)
    if size:
        parts.append(size)
    head = {"Keep": "Nothing to do.", "Add": "Add.", "Stop adding": "Stop adding.", "Switch": "Switch.", "Review": "Review."}[call]
    return " ".join([head] + [p for p in parts if p])


def decide(db, as_of: date, analyse, runners: list[str], exit_loads: dict | None = None) -> dict:
    rows = facts(db, as_of, exit_loads)
    screened = {r["id"]: screen(db, r, as_of) for r in rows}
    short = shortlist(rows, screened)
    answers, failures, runner_name, asked = {}, [], None, False
    if short:
        asked = True
        brief = brief_for(short, screened)
        try:
            got = analyse(brief, "fund_forecast", runners)
            runner_name, failures = got["runner"], got.get("failures", [])
            by_id = {r["id"]: r for r in short}
            for it in got["decisions"]["items"]:
                if it["id"] in by_id and it["stance"] in STANCES:
                    answers[it["id"]] = it
        except runner.RunnerError as err:
            failures.append({"runner": "fund_forecast", "error": str(err)[:500]})
    calls = []
    for r in rows:
        s = screened[r["id"]]
        ans = answers.get(r["id"]) if r["id"] in {x["id"] for x in short} else None
        model = None
        if ans:
            base = r["base_rate"] and r["base_rate"]["rate"]
            model = {"probability": _clamp_chance(ans["probability"], base), "stance": ans["stance"]}
        asked_this = r["id"] in {x["id"] for x in short}
        if asked_this:
            final, change = combine(s["call"], model, bool(r["base_rate"]))
        else:
            final, change = s["call"], ""
        reason = _plain(ans["reason"]) if ans else ""
        calls.append({"row": r, "screen": s, "call": final, "model": model, "line": line_for(r, final, s, change, reason),
                      "asked": asked_this, "model_reason": reason})
    return {"calls": calls, "asked": asked, "runner": runner_name, "failures": failures, "shortlist": [r["id"] for r in short]}


# ---- storing, scoring, the dashboard -----------------------------------------------------------------------

def _store(db, day: date, result: dict) -> None:
    db.execute("begin")
    try:
        db.execute("delete from fund_calls where made_on = ?", [day])
        for c in result["calls"]:
            r, s = c["row"], c["screen"]
            if not r["judged"]:
                continue
            sw = s["switch"] if c["call"] == "Switch" else None
            same_fund = bool(sw and sw["kind"] == "direct_twin")
            target_code = None
            if sw:
                target_code = (r["twin"] if same_fund else r.get("peer_target"))["code"]
            detail = {"switch": sw and {k: v for k, v in sw.items() if k != "ok"}, "sip": r["sip"], "same_fund": same_fund,
                      "consistency": r["consistency"], "base_rate_note": r["base_rate_note"], "model_reason": c["model_reason"]}
            m = c["model"]
            db.execute("""insert into fund_calls (made_on, isin, scheme_code, name, category, call, code_call, model_stance,
                          probability, base_rate, base_rate_n, line, detail, nav, compare_code, runner)
                          values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                       [day, r["isin"], r["code"], r["name"], r["category"], c["call"], s["call"], m and m["stance"],
                        m and m["probability"], r["base_rate"] and r["base_rate"]["rate"], r["base_rate"] and r["base_rate"]["n"],
                        c["line"], json.dumps(detail, default=str), r["price"], None if same_fund else target_code, result["runner"]])
            c["detail"] = detail
        db.execute("commit")
    except Exception:
        db.execute("rollback")
        raise


def _peer_middle(db, category: str, exclude: int, start: date, end: date) -> float | None:
    rets = []
    for (code,) in db.execute("select scheme_code from funds where category = ? and plan like 'Direct%' and option like '%Growth%' "
                              "and scheme_code <> ?", [category, exclude]).fetchall():
        a, b = fundreview._nav_on(db, code, start), fundreview._nav_on(db, code, end)
        if a and b:
            rets.append(b / a - 1)
    return median(rets) if len(rets) + 1 >= fundreview.MIN_PEERS else None


def score(db, today: date) -> int:
    """Fill score_1m/3m/6m (1.0 = the call was right) once a window has ended. Keep and Add are right when the fund beat its
    category's middle fund; Stop adding and Review when it did not; a Switch to another fund when that fund beat the held one.
    A Switch to the same fund's Direct plan is a cost call and is not scored."""
    filled = 0
    for column, days, _ in record.WINDOWS:
        due = db.execute(f"select id, made_on, scheme_code, category, call, compare_code, detail from fund_calls "
                         f"where {column} is null and made_on + ? <= ?", [days, today]).fetchall()
        for call_id, made_on, code, category, call, compare, detail in due:
            end = made_on + timedelta(days=days)
            if json.loads(detail or "{}").get("same_fund"):
                continue
            a, b = fundreview._nav_on(db, code, made_on), fundreview._nav_on(db, code, end)
            if not (a and b):
                continue
            mine = b / a - 1
            if call == "Switch":
                if not compare:
                    continue
                ca, cb = fundreview._nav_on(db, compare, made_on), fundreview._nav_on(db, compare, end)
                if not (ca and cb):
                    continue
                right = (cb / ca - 1) > mine
            else:
                middle = _peer_middle(db, category, code, made_on, end)
                if middle is None:
                    continue
                right = (mine > middle) if call in ("Keep", "Add") else (mine <= middle)
            db.execute(f"update fund_calls set {column} = ? where id = ?", [1.0 if right else 0.0, call_id])
            filled += 1
    return filled


def summary(db) -> dict:
    out = {"scored_3m": db.execute("select count(*) from fund_calls where score_3m is not null").fetchone()[0], "by_call": {}}
    for call, n, right in db.execute("select call, count(score_3m), avg(score_3m) from fund_calls group by call").fetchall():
        out["by_call"][call] = {"scored": n, "right": right}
    out["unproven"] = out["scored_3m"] < record.PROVEN_AFTER
    return out


def _entry(c: dict) -> dict:
    r, m = c["row"], c["model"]
    sw = (c.get("detail") or {}).get("switch")
    return {"isin": r["isin"], "name": r["name"], "verdict": c["call"], "why": c["line"], "call": c["call"], "line": c["line"],
            "code_call": c["screen"]["call"], "category": r["category"], "judged": r["judged"],
            "base_rate": r["base_rate"] and {"rate": round(r["base_rate"]["rate"], 3), "n": r["base_rate"]["n"],
                                              "cost_drag": r["base_rate"]["cost_drag"]},
            "chance": m and m["probability"], "switch": sw, "sip": r["sip"]}


def run(db, day: date, analyse, runners: list[str], exit_loads: dict | None = None) -> dict:
    """The weekly step: base rates, calls, storage, scoring, and the dashboard's two payloads."""
    rates = base_rates(db, day)
    save_base_rates(db, rates, day)
    result = decide(db, day, analyse, runners, exit_loads)
    _store(db, day, result)
    scored = score(db, day)
    entries = [_entry(c) for c in result["calls"]]
    db.execute("insert or replace into weekly_reports values (?, 'fund_calls', ?)", [day, json.dumps({"as_of": day, "calls": entries}, default=str)])
    return {"funds": len(entries), "asked_model": result["asked"], "runner": result["runner"], "failures": result["failures"],
            "calls": {k: sum(e["call"] == k for e in entries) for k in CALLS}, "scored": scored, "base_rate_cells": len(rates)}


def site_payload(db) -> dict:
    row = db.execute("select week_of, payload from weekly_reports where section = 'fund_calls' order by week_of desc limit 1").fetchone()
    body = json.loads(row[1]) if row else {"as_of": None, "calls": []}
    rates = [{"group": g, "quartile": q, "n": n, "periods": p, "hit_rate": round(h, 3), "avg_excess": round(x, 4),
              "cost_drag": c} for g, q, n, p, h, x, c in db.execute(
        "select group_name, quartile, n, periods, hit_rate, avg_excess, cost_drag from fund_base_rates "
        "where horizon_days = ? order by group_name, quartile", [HORIZON_DAYS]).fetchall()]
    text = ("Nothing to do this week." if body["calls"] and all(c["call"] == "Keep" for c in body["calls"])
            else "The fund review runs on Saturday." if not body["calls"] else
            "; ".join(f"{k}: {n}" for k in CALLS if (n := sum(c["call"] == k for c in body["calls"]))) + ".")
    return {"as_of": body["as_of"], "headline": text, "calls": body["calls"], "base_rates": rates, "base_rate_caveat": CAVEAT,
            "record": summary(db)}
