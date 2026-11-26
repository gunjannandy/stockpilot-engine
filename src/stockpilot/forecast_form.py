"""The model's strict forecast form, the twelve code checks, and the call code makes from it (T17, spec #24).

The code gives the start (`brief["base"]`, from the mechanical engine). The model returns adjustments in points from a fixed
menu; code checks the form and does the arithmetic. A model can move a chance, never overwrite the start, and never make a
buy that the numbers do not allow.

    forecast_stock(brief, analyse, rules) -> record     one stock, one record, ready for the `calls` table and the archive

`analyse(brief, role, errors=None)` is the model seam (the real one is the VM's model chain, the test one a fake). Roles:
"forecast" returns {"model", "form"}; "second_opinion" returns {"model", "net": {"m3", "m6"}}.

Chances in the form are whole percents; the record uses fractions like the contract (`chance_3m` 0.58).
Sells stay with v1's rules (`calls/decide.py`): this module only says `buy` or `wait`.

The twelve checks (each is a function below, in this order):
  1 form       2 chance sum and caps     3 ranges        4 evidence ids      5 mechanical areas  6 already in price
  7 counts     8 direction (a flag)      9 Bengali      10 numbers and dates 11 second opinion   12 the record
"""
import re
from datetime import date

from stockpilot import reasoning

ITEM_CAP = 5                         # points one adjustment may move a chance
TOTAL_CAP = {"m3": 12, "m6": 15}     # points all adjustments together may move it
HORIZONS = ("m3", "m6")
RANGE_HORIZONS = ("m1", "m3", "m6")
MECHANICAL_AREAS = {"trend", "value", "quality"}       # already in the starting chance: the model may not count them again
ADJUST_AREAS = {"news", "owners", "results", "sector", "risk", "other"}
REASON_AREAS = ADJUST_AREAS | MECHANICAL_AREAS
CALLS = {"buy", "add", "hold", "trim", "sell", "watch", "wait", "nothing"}
CONFIDENCE = {"low", "medium", "high"}
VERDICT_HISTORY = {"strong", "steady", "patchy", "weak", "unknown"}
VERDICT_WEIGHT = {"heavy", "middle", "light", "unknown"}
EFFECTS = {"up", "down", "none", "unclear"}
IN_PRICE = {"yes", "no", "unsure"}
MAX_REASONS, MAX_NEWS, MAX_VIEW, MAX_RISKS = 3, 5, 3, 3
RANGE_SLACK = 1.5                    # the model's range may sit this far from the code's, in either direction
CHANCE_LO, CHANCE_HI = 5, 95
ROUNDING = 1                         # points of slack when the chance is checked against start + adjustments
SPREAD_CAP = 15                      # the 6-month chance may differ from the 3-month one by at most this

TOP_KEYS = {"call", "confidence", "chance", "range", "company_history", "market_weight", "news", "reasons_for",
            "reasons_against", "adjustments", "would_change_view", "risks", "summary", "summary_bn", "broken_reason"}
BENGALI = re.compile(r"[ঀ-৿]")
ISO_DATE = re.compile(r"\b(\d{4}-\d{2}-\d{2})\b")
LATIN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")


# ---------------------------------------------------------------- helpers
def _num(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and x == x


def _pct(x: float) -> int:
    return round(x * 100)


def _news_by_id(brief: dict) -> dict:
    return {n["id"]: n for n in brief.get("news") or []}


def confirmed_ids(brief: dict) -> set[str]:
    """A news event is confirmed when it is high impact and a filing, or two or more sources, say so."""
    return {n["id"] for n in brief.get("news") or []
            if n.get("impact") == "high" and (n.get("filing") or (n.get("sources") or 0) >= 2)}


def _sentences(form: dict):
    """Every (english, bengali, label) pair the reader may see."""
    for k in ("company_history", "market_weight"):
        b = form.get(k) or {}
        yield b.get("line"), b.get("line_bn"), k
    for n in form.get("news") or []:
        yield n.get("what_happened"), n.get("what_happened_bn"), "news"
    for side in ("reasons_for", "reasons_against"):
        for r in form.get(side) or []:
            yield r.get("text"), r.get("text_bn"), side
    for side in ("would_change_view", "risks"):
        for r in form.get(side) or []:
            yield r.get("text"), r.get("text_bn"), side
    yield form.get("summary"), form.get("summary_bn"), "summary"


def _pool(brief: dict, form: dict) -> set[str]:
    chances = {"m3": brief["base"].get("chance_3m"), "m6": brief["base"].get("chance_6m")}
    extra = {"base_pct": [_pct(v) for v in chances.values() if _num(v)], "price": brief.get("price"),
             "final": form.get("chance"), "range": form.get("range")}
    return reasoning.number_pool(brief.get("facts"), brief.get("base"), brief.get("news"), extra)


def _sum(form: dict, horizon: str, only=None, skip=None) -> int:
    return sum(a["points"] for a in form.get("adjustments") or []
               if a.get("horizon") == horizon and (only is None or a["from_evidence"] in only)
               and (skip is None or a["from_evidence"] not in skip))


# ---------------------------------------------------------------- the checks; each returns a list of plain errors
def check_form(form: dict) -> list[str]:                                        # 1
    if not isinstance(form, dict):
        return ["The form is not an object."]
    errs = []
    extra, missing = set(form) - TOP_KEYS, TOP_KEYS - set(form)
    if extra:
        errs.append(f"Extra keys in the form: {sorted(extra)}.")
    if missing:
        errs.append(f"Missing keys in the form: {sorted(missing)}.")
    if errs:
        return errs
    enums = [(form["call"], CALLS, "call"), (form["confidence"], CONFIDENCE, "confidence"),
             ((form["company_history"] or {}).get("verdict"), VERDICT_HISTORY, "company_history.verdict"),
             ((form["market_weight"] or {}).get("verdict"), VERDICT_WEIGHT, "market_weight.verdict")]
    for v, allowed, name in enums:
        if v not in allowed:
            errs.append(f"{name} is {v!r}; it must be one of {sorted(allowed)}.")
    ch = form["chance"]
    if not isinstance(ch, dict) or set(ch) != set(HORIZONS) or not all(_num(ch[h]) and 0 <= ch[h] <= 100 for h in HORIZONS):
        errs.append("chance must hold m3 and m6 as numbers from 0 to 100.")
    rg = form["range"]
    if not isinstance(rg, dict) or set(rg) != set(RANGE_HORIZONS) or not all(
            isinstance(rg[h], dict) and set(rg[h]) == {"low", "likely", "high"} and all(_num(v) for v in rg[h].values())
            for h in RANGE_HORIZONS):
        errs.append("range must hold m1, m3 and m6, each with low, likely and high numbers.")
    for side in ("reasons_for", "reasons_against"):
        for r in form[side] if isinstance(form[side], list) else []:
            if not isinstance(r, dict) or r.get("area") not in REASON_AREAS or r.get("horizon") not in HORIZONS \
                    or not isinstance(r.get("evidence_ids"), list) or not _num(r.get("points")) or not 0 <= r["points"] <= ITEM_CAP:
                errs.append(f"A {side} item is malformed.")
    for a in form["adjustments"] if isinstance(form["adjustments"], list) else []:
        if not isinstance(a, dict) or set(a) != {"area", "from_evidence", "points", "horizon"} or a["horizon"] not in HORIZONS \
                or a["area"] not in ADJUST_AREAS | MECHANICAL_AREAS or not _num(a["points"]) or a["points"] != int(a["points"]):
            errs.append("An adjustment is malformed (area, from_evidence, whole points, horizon m3 or m6).")
    for n in form["news"] if isinstance(form["news"], list) else []:
        if not isinstance(n, dict) or n.get("effect") not in EFFECTS or n.get("already_in_price") not in IN_PRICE \
                or n.get("horizon") not in RANGE_HORIZONS:
            errs.append("A news item is malformed.")
    for k in ("reasons_for", "reasons_against", "adjustments", "news", "would_change_view", "risks"):
        if not isinstance(form[k], list):
            errs.append(f"{k} must be a list.")
    return errs


def check_chance_and_caps(form: dict, brief: dict) -> list[str]:                # 2
    errs, confirmed = [], confirmed_ids(brief)
    for a in form["adjustments"]:
        if abs(a["points"]) > ITEM_CAP and a["from_evidence"] not in confirmed:
            errs.append(f"An adjustment of {a['points']} points is over the {ITEM_CAP} points allowed for one item.")
    for h in HORIZONS:
        base = _pct(brief["base"][f"chance_{h[1:]}m"])
        capped = _sum(form, h, skip=confirmed)
        if abs(capped) > TOTAL_CAP[h]:
            errs.append(f"The {h[1:]}-month adjustments total {capped} points; the limit is {TOTAL_CAP[h]}.")
        want = min(CHANCE_HI, max(CHANCE_LO, base + _sum(form, h)))
        if abs(form["chance"][h] - want) > ROUNDING:
            errs.append(f"The {h[1:]}-month chance {form['chance'][h]} does not add up: start {base} plus adjustments is {want}.")
    return errs


def check_ranges(form: dict, brief: dict) -> list[str]:                         # 3
    errs = []
    for h in RANGE_HORIZONS:
        r, base = form["range"][h], brief["base"]
        if not r["low"] < r["likely"] < r["high"]:
            errs.append(f"The {h[1:]}-month range is not low < likely < high.")
        for k in ("low", "likely", "high"):
            code = base.get(f"{k}_{h[1:]}m")
            if code and not (code / RANGE_SLACK <= r[k] <= code * RANGE_SLACK):
                errs.append(f"The {h[1:]}-month {k} {r[k]} is too far from the data's {code}.")
    return errs


def check_evidence(form: dict, brief: dict) -> list[str]:                       # 4
    today, known = brief["as_of"], {n["id"]: n["date"] for n in brief.get("news") or []}
    known.update({k: v.get("date") for k, v in (brief.get("facts") or {}).items()})
    ids = [i for side in ("reasons_for", "reasons_against") for r in form[side] for i in r["evidence_ids"]]
    ids += [a["from_evidence"] for a in form["adjustments"]] + [n.get("id") for n in form["news"]]
    ids += [i for k in ("company_history", "market_weight") for i in form[k].get("facts_used") or []]
    errs = []
    for i in dict.fromkeys(ids):
        if i not in known:
            errs.append(f"Evidence {i!r} is not in the brief.")
        elif known[i] and str(known[i]) > today:
            errs.append(f"Evidence {i!r} is dated {known[i]}, after today ({today}).")
    for r in form["reasons_for"] + form["reasons_against"]:
        if not r["evidence_ids"]:
            errs.append("A reason names no evidence.")
    return errs


def check_mechanical_areas(form: dict) -> list[str]:                            # 5
    return [f"The {a['area']} area is already in the starting chance; it takes no adjustment."
            for a in form["adjustments"] if a["area"] in MECHANICAL_AREAS and a["points"]]


def check_already_in_price(form: dict) -> list[str]:                            # 6
    priced = {n["id"] for n in form["news"] if n["already_in_price"] == "yes"}
    return [f"News {a['from_evidence']!r} is already in the price; it moves nothing."
            for a in form["adjustments"] if a["from_evidence"] in priced and a["points"]]


def check_counts(form: dict) -> list[str]:                                      # 7
    errs = []
    for k, cap in (("reasons_for", MAX_REASONS), ("reasons_against", MAX_REASONS), ("news", MAX_NEWS),
                   ("would_change_view", MAX_VIEW), ("risks", MAX_RISKS)):
        if len(form[k]) > cap:
            errs.append(f"{k} has {len(form[k])} items; the most is {cap}.")
    return errs


def spread_errors(form: dict, brief: dict) -> list[str]:
    if abs(form["chance"]["m6"] - form["chance"]["m3"]) > SPREAD_CAP and not confirmed_ids(brief):
        return [f"The 6-month chance is more than {SPREAD_CAP} points from the 3-month chance."]
    return []


def direction_flag(form: dict) -> str | None:                                   # 8: a flag, recorded, never a rejection
    net = _sum(form, "m3") + _sum(form, "m6")
    up = sum(r["points"] for r in form["reasons_for"])
    down = sum(r["points"] for r in form["reasons_against"])
    if (net > 0 and down > up) or (net < 0 and up > down):
        return "The adjustments lean against the weight of the reasons given."
    return None


def check_bengali(form: dict) -> list[str]:                                     # 9
    errs = []
    for en, bn, label in _sentences(form):
        if not isinstance(en, str) or not en.strip():
            errs.append(f"A {label} sentence is empty.")
        elif not isinstance(bn, str) or not BENGALI.search(bn):
            errs.append(f"A {label} sentence has no Bengali.")
        else:
            gone = [n for n in reasoning.numbers(en) if n not in reasoning.numbers(bn.translate(LATIN_DIGITS))]
            if gone:
                errs.append(f"The Bengali of a {label} sentence drops the numbers {gone}.")
    return errs


def check_numbers_and_dates(form: dict, brief: dict) -> list[str]:              # 10
    pool, errs = _pool(brief, form) | {"100"}, []
    for en, _, label in _sentences(form):
        text = en or ""
        for d in ISO_DATE.findall(text):
            if d > brief["as_of"]:
                errs.append(f"A {label} sentence names {d}, after today.")
        stripped = ISO_DATE.sub(" ", text)
        for n in reasoning.numbers(stripped):
            if n not in pool:
                errs.append(f"The number {n} in a {label} sentence is not in the data.")
    return list(dict.fromkeys(errs))


def validate(form: dict, brief: dict) -> tuple[list[str], list[str]]:
    """(errors, flags). Any error rejects the form."""
    errs = check_form(form)
    if errs:
        return errs, []
    errs = (check_chance_and_caps(form, brief) + check_ranges(form, brief) + check_evidence(form, brief)
            + check_mechanical_areas(form) + check_already_in_price(form) + check_counts(form)
            + spread_errors(form, brief) + check_bengali(form) + check_numbers_and_dates(form, brief))
    flag = direction_flag(form)
    return errs, [flag] if flag else []


# ---------------------------------------------------------------- what code makes of a good form
def needs_second_opinion(p3: float, rules) -> bool:
    return min(abs(p3 - rules.buy_at), abs(p3 - rules.sell_at)) <= rules.borderline + 1e-9


def shrink(net: float, asked: float) -> float:                                  # 11
    """The second opinion may only move a net adjustment toward zero. Growing it, or flipping it, is ignored."""
    if not _num(asked) or net == 0 or asked * net < 0:
        return 0 if (_num(asked) and net and asked * net < 0) else net
    return asked if abs(asked) < abs(net) else net


def _decide(brief: dict, rules, net3: float, net6: float, form: dict) -> dict:
    base3, base6 = brief["base"]["chance_3m"], brief["base"]["chance_6m"]
    confirmed = confirmed_ids(brief)
    used_confirmed = {a["from_evidence"] for a in form["adjustments"]
                      if a["from_evidence"] in confirmed and a["points"] > 0}
    p3 = min(CHANCE_HI, max(CHANCE_LO, _pct(base3) + net3)) / 100
    p6 = min(CHANCE_HI, max(CHANCE_LO, _pct(base6) + net6)) / 100
    # Without a confirmed event the start decides which side of the buy line the call may land on.
    own3 = min(CHANCE_HI, max(CHANCE_LO, _pct(base3) + _sum(form, "m3", skip=confirmed))) / 100
    capped = False
    if base3 < rules.buy_at and not used_confirmed and p3 >= rules.buy_at:
        p3, capped = round(rules.buy_at - 0.01, 2), True
    buy = p3 >= rules.buy_at
    news_buy = buy and bool(used_confirmed) and (base3 < rules.buy_at or own3 < rules.buy_at)
    return {"chance_3m": round(p3, 2), "chance_6m": round(p6, 2), "call": "buy" if buy else "wait",
            "news_buy": news_buy, "route": "news" if news_buy else "code", "capped_below_floor": capped}


def _fallback(brief: dict, why: list[str]) -> dict:
    b = brief["base"]
    return {"chance_3m": b["chance_3m"], "chance_6m": b["chance_6m"], "call": "wait", "news_buy": False,
            "route": "code", "capped_below_floor": False, "unavailable": "model unavailable", "why": why}


def _ranges(form: dict) -> dict:
    return {f"{k}_{h[1:]}m": form["range"][h][k] for h in RANGE_HORIZONS for k in ("low", "likely", "high")}


def forecast_stock(brief: dict, analyse, rules) -> dict:
    """Ask the model, check the form (one retry with the errors), apply the second opinion near a line, and make the call."""
    record = {"symbol": brief["symbol"], "as_of": brief["as_of"], "base": dict(brief["base"]), "status": "rejected",
              "errors": [], "flags": [], "raw": None, "model": None, "second_opinion_model": None,
              "second_opinion": None, "attempts": 0}
    errors = None
    for _ in range(2):
        got = analyse(brief, "forecast", errors=errors) if errors else analyse(brief, "forecast")
        record["attempts"] += 1
        form, record["model"] = got.get("form"), (got.get("model") or None)
        record["raw"] = form
        errs, flags = validate(form, brief)
        if not record["model"]:                                                 # 12: every forecast records its model
            errs.append("The record names no model.")
        record["errors"], record["flags"] = errs, flags
        if not errs:
            break
        errors = errs
    if record["errors"]:
        return {**record, **_fallback(brief, record["errors"])}

    net3, net6 = _sum(form, "m3"), _sum(form, "m6")
    out = _decide(brief, rules, net3, net6, form)
    if needs_second_opinion(out["chance_3m"], rules):
        sec = analyse(brief, "second_opinion", forecast=form, net={"m3": net3, "m6": net6})
        asked = sec.get("net") or {}
        n3, n6 = shrink(net3, asked.get("m3")), shrink(net6, asked.get("m6"))
        record["second_opinion"], record["second_opinion_model"] = {"m3": n3, "m6": n6}, sec.get("model")
        out = _decide(brief, rules, n3, n6, form)
    return {**record, **out, "status": "ok", "confidence": form["confidence"], "summary": form["summary"],
            "summary_bn": form["summary_bn"], "ranges": _ranges(form)}
