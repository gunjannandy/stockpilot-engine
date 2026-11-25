"""The `reasoning` object: why we think what we think about one stock, in plain words, for every stock the site shows.

Contract: `docs/build-lanes-v11.md` (F1) and `schemas/site-contract.md`. One pure builder (`build`), no database and no
network, so the site, the stock files and the tests all get the same answer. Code items come from the screen's four scores
(each a percentile inside the stock's own sector) and carry the numbers behind them; analyst items come from the model's
`moved_by` and its new `for`/`against` lists, and survive only when every number in them is in the brief
(`clean_analyst_items`, the same idea as the `_bn` check)."""
import re
from datetime import date

AREAS = ("trend", "value", "quality", "growth", "risk", "news", "owners", "results", "flow", "sector", "tax", "size")
MAX_SIDE = 5            # items per side in the object
MAX_ANALYST = 3         # items per side the analyst may add
MAX_FACTS, MAX_CHANGE = 6, 5
THIN_N = 30             # a base rate resting on fewer cases is "limited evidence"
EDGE = 0.15             # a sector percentile this far from the middle is worth a line
POINTS = {"quality": 3.0, "value": 2.5, "momentum": 3.0, "risk": 1.5}     # the screen's weights x 10: percentage points at the extreme
AREA_OF = {"quality": "quality", "value": "value", "momentum": "trend", "risk": "risk"}
STANCE = {"buy": "buy", "add": "buy", "hold": "hold", "keep": "hold", "watch": "watch", "follow": "watch",
          "sell": "sell", "trim": "sell"}
KEYWORDS = (("value", ("pe ", "cheap", "expensive", "valuation", "price to", "earnings multiple", "pricey")),
            ("quality", ("return on", "roe", "roce", "debt", "margin", "quality")),
            ("growth", ("growth", "grow", "profit", "sales", "revenue", "order")),
            ("results", ("result", "quarter", "earnings")),
            ("owners", ("promoter", "pledge", "stake", "holding", "shareholding")),
            ("flow", ("volume", "delivery", "buying", "selling", "fii", "dii", "deal")),
            ("sector", ("sector", "industry", "peers")),
            ("tax", ("tax", "long-term gain", "short-term")),
            ("size", ("size", "position", "concentration", "limit")),
            ("trend", ("trend", "momentum", "run-up", "rally", "average", "high", "low", "price")),
            ("risk", ("risk", "volatil", "swing", "pledge", "debt", "regulat")))
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
FACT_SOURCES = (("range52", "sentence", "trend"), ("volume", "sentence", "flow"), ("delivery", "sentence", "flow"),
                ("ownership", "sentence", "owners"), ("results", "sentence", "results"), ("surveillance", "sentence", "risk"),
                ("headlines_note", None, "news"), ("deals_note", None, "flow"), ("announcements_note", None, "news"))


# ---- numbers: every number in a sentence must come from the inputs ------------------------------------------------------

def _norm(raw: str) -> str:
    x = float(raw.replace(",", "").rstrip("."))
    return str(int(x)) if x == int(x) else f"{x:.6f}".rstrip("0")


# A period named in a standard label, not a figure the data must hold: "52-week high", "52 weeks", "52-wk", "12-month low".
PERIOD_LABEL = re.compile(r"(?<![\d.,])(?:52[\s\-\u2010-\u2015]*(?:weeks?|wks?|w)\b|12[\s\-\u2010-\u2015]*months?\b)", re.I)


def numbers(text: str) -> list[str]:
    text = PERIOD_LABEL.sub(" ", text or "")
    return [_norm(m.group()) for m in NUMBER.finditer(text)]


def _renderings(v: float) -> set[str]:
    out = set()
    for scale in ((1, 100) if abs(v) <= 2 else (1,)):      # only a fraction has a percent form; a price of 48.12 is not 4812%
        for nd in (0, 1, 2, 3):
            out.add(_norm(f"{abs(v * scale):.{nd}f}"))
    if 0 <= v <= 1:
        out.add(_norm(f"{100 - 100 * v:.0f}"))      # "pricier than 2% of its sector" from a score of 0.98
    return out


def number_pool(*docs) -> set[str]:
    """Every number in the documents, as it may be written: rounded, as a percent, from inside a string."""
    pool: set[str] = set()

    def walk(x):
        if isinstance(x, bool) or x is None:
            return
        if isinstance(x, (int, float)):
            if x == x and abs(x) != float("inf"):
                pool.update(_renderings(float(x)))
        elif isinstance(x, str):
            pool.update(numbers(x))
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
    for d in docs:
        walk(d)
    return pool


def _sentences(r: dict):
    for side in ("for", "against", "facts", "change_view"):
        for i in r.get(side) or []:
            yield i.get("text")
    yield r.get("headline")
    yield (r.get("chance") or {}).get("explain")


def untraced(r: dict, pool: set[str]) -> list[str]:
    """Numbers written in the object's sentences that are not in `pool`, each once, in order."""
    out: list[str] = []
    pool = pool | {"100"} | number_pool([i.get("level") for i in r.get("change_view") or []])     # "Out of 100"; a level code worked out
    for text in _sentences(r):
        for n in numbers(text or ""):
            if n not in pool and n not in out:
                out.append(n)
    return out


def _area(text: str, default: str = "news") -> str:
    low = f" {(text or '').lower()} "
    return next((area for area, words in KEYWORDS if any(w in low for w in words)), default)


def clean_analyst_items(items, brief: dict, side: str) -> tuple[list[dict], list[str]]:
    """The analyst's `for`/`against` items that pass: a plain sentence, a known area, every number found in the brief. At
    most three. Returns (kept, why each dropped one was dropped)."""
    pool, kept, dropped = number_pool(brief), [], []
    for it in items or []:
        text = (it.get("text") or "").strip() if isinstance(it, dict) else ""
        if not text:
            dropped.append(f"{side}: empty item")
            continue
        bad = [n for n in numbers(text) if n not in pool]
        if bad:
            dropped.append(f"{side}: '{', '.join(bad)}' is not in the brief ({text[:60]})")
            continue
        if len(kept) >= MAX_ANALYST:
            dropped.append(f"{side}: more than {MAX_ANALYST} items")
            continue
        area = it.get("area") if it.get("area") in AREAS else _area(text)
        points = it.get("points")
        weight = None if not isinstance(points, (int, float)) else round(abs(points) * (1 if side == "for" else -1), 1)
        kept.append({"text": text, "area": area, "by": "analyst", "weight": weight,
                     "news_used": [n for n in it.get("news_used") or [] if isinstance(n, str)]})
    return kept, dropped


# ---- the pieces ---------------------------------------------------------------------------------------------------------

def _pp(n):
    return f"{n:+.1f}"


def _code_items(c: dict, sector: dict | None) -> tuple[list[dict], list[dict]]:
    """For and against lines from the screen: each score is a percentile inside the stock's sector."""
    m, scores = c.get("metrics") or {}, c.get("scores") or {}
    sector = sector or {}
    out_for, out_against = [], []
    for factor, score in scores.items():
        if score is None or abs(score - 0.5) < EDGE:
            continue
        pct, up = round(100 * score), score > 0.5
        rest = 100 - pct
        if factor == "value":
            pe, med = m.get("pe"), sector.get("pe")
            tail = f" (PE {pe:.0f} against {med:.0f})" if pe and med and pe > 0 else ""
            text = f"Cheaper than {pct}% of its sector{tail}" if up else f"Pricier than {rest}% of its sector{tail}"
        elif factor == "quality":
            roe = m.get("roe")
            tail = f" (it earns {100 * roe:.0f}% a year on its owners' money)" if roe is not None else ""
            text = f"Better run than {pct}% of its sector{tail}" if up else f"Weaker returns and more debt than {rest}% of its sector{tail}"
        elif factor == "momentum":
            bits = []
            if m.get("ret_6m") is not None:
                bits.append(f"{100 * m['ret_6m']:+.0f}% in 6 months")
            d = m.get("dist_200dma")
            if d is not None:
                bits.append(f"{100 * abs(d):.0f}% {'above' if d > 0 else 'under'} its 200-day average")
            tail = f" ({', '.join(bits)})" if bits else ""
            text = f"Price trend stronger than {pct}% of its sector{tail}" if up else f"Price trend weaker than {rest}% of its sector{tail}"
        else:
            vol = m.get("vol_1y")
            tail = f" (it swings {100 * vol:.0f}% a year)" if vol is not None else ""
            text = f"Steadier than {pct}% of its sector{tail}" if up else f"Wilder swings than {rest}% of its sector{tail}"
        item = {"text": text, "weight": round((score - 0.5) * 2 * POINTS[factor], 1), "area": AREA_OF[factor], "by": "code"}
        (out_for if up else out_against).append(item)
    return out_for, out_against


def _reasons(call: dict) -> dict:
    r = call.get("reasons")
    return r if isinstance(r, dict) else {}


def _analyst_items(call: dict) -> tuple[list[dict], list[dict]]:
    r = _reasons(call)
    moved = call.get("moved_by") or (r.get("moved_by") if isinstance(r.get("moved_by"), list) else None) or \
        (call["reasons"] if isinstance(call.get("reasons"), list) else [])
    out_for, out_against = [], []
    for mv in moved:
        pts, why = mv.get("points"), (mv.get("reason") or "").strip()
        if not why or not isinstance(pts, (int, float)) or pts == 0:
            continue
        item = {"text": why, "weight": round(pts, 1), "area": _area(why), "by": "analyst"}
        (out_for if pts > 0 else out_against).append(item)
    for side, bucket in (("for", out_for), ("against", out_against)):
        for it in r.get(side) or []:
            if isinstance(it, dict) and it.get("text"):
                bucket.append({"text": it["text"], "weight": it.get("weight"), "area": it.get("area") if it.get("area") in AREAS else _area(it["text"]),
                               "by": "analyst", **({"news_used": it["news_used"]} if it.get("news_used") else {})})
    return out_for, out_against


def _merge(analyst: list[dict], code: list[dict], asof: str) -> list[dict]:
    """The analyst's line wins over code's on the same area; strongest first; at most five."""
    taken = {i["area"] for i in analyst}
    items = analyst + [i for i in code if i["area"] not in taken]
    items.sort(key=lambda i: -abs(i["weight"] or 0))
    return [{**i, "asof": asof} for i in items[:MAX_SIDE]]


def _facts(stock: dict | None) -> list[dict]:
    out = []
    for key, sub, area in FACT_SOURCES:
        v = (stock or {}).get(key)
        text = v.get(sub) if sub and isinstance(v, dict) else (v if isinstance(v, str) else None)
        if text:
            out.append({"text": text, "area": area})
    return out[:MAX_FACTS]


def _why_parts(why: str | None) -> tuple[str | None, str | None]:
    """The stop's and the target's reasons out of the levels sentence: "If it falls to ₹X (stop reason), sell. Aim for ₹Y (target reason)."."""
    m = re.search(r"falls to ₹[\d,\.]+ \((.+?)\), sell\. Aim for ₹[\d,\.]+ \((.+?)\)\.?$", why or "")
    return (m.group(1), m.group(2)) if m else (None, None)


def _levels(call: dict) -> dict | None:
    if not call or not (call.get("entry") and call.get("stop") and call.get("target")):
        return None
    r = _reasons(call)
    stop_why, target_why = _why_parts(r.get("levels_why") or call.get("levels_why"))
    out = {"entry": call["entry"], "stop": call["stop"], "target": call["target"]}
    for k, v in (("stop_why", stop_why), ("target_why", target_why), ("target_hit_rate", r.get("target_hit_rate")),
                 ("target_hit_n", r.get("target_hit_n"))):
        if v is not None:
            out[k] = v
    return out


def _chance(call: dict, up: list[dict], down: list[dict]) -> dict | None:
    p = call.get("probability")
    if p is None:
        return None
    base, n = call.get("base_rate"), call.get("base_rate_n")
    hurdle = call.get("hurdle_pct")
    if hurdle is None and call.get("hurdle") is not None:
        hurdle = round(100 * call["hurdle"], 2)
    out = {"p": round(p, 4)}
    if base is not None:
        out["base_rate"] = round(base, 4)
    if n is not None:
        out["n"] = int(n)
    if hurdle is not None:
        out["hurdle_pct"] = hurdle
    moves = sorted((i for i in up + down if i["by"] == "analyst" and i["weight"]), key=lambda i: -abs(i["weight"]))[:2]
    text = f"Out of 100 stocks like this, {round(100 * p)} beat the Nifty"
    text += f" by {hurdle:g}% or more over three months." if hurdle else " over three months."
    if moves:
        parts = [f"{_pp(i['weight'])} for {i['text'][:1].lower() + i['text'][1:].rstrip('.')}" for i in moves]
        text += f" We started from {round(100 * base)} and moved it by {' and '.join(parts)}." if base is not None else \
            f" We moved it by {' and '.join(parts)}."
    out["explain"] = text
    return out


def _change_view(call: dict | None, c: dict | None, stock: dict | None, trigger: str | None) -> list[dict]:
    out = []
    if call and call.get("would_buy_if"):
        out.append({"text": call["would_buy_if"], "turns": "buy"})
    if call and call.get("level_flag"):
        out.append({"text": call["level_flag"]})
    if trigger:
        out.append({"text": trigger, "turns": "buy"})
    m = (c or {}).get("metrics") or {}
    d, close = m.get("dist_200dma"), m.get("close")
    if d is not None and close and not trigger:
        if d < 0:
            level = close / (1 + d)
            out.append({"text": f"A close above ₹{level:,.0f} (its 200-day average) would lift its trend score.", "level": round(level, 2), "turns": "buy"})
        elif d < 0.08:
            level = close / (1 + d)
            out.append({"text": f"A close below ₹{level:,.0f} (its 200-day average) would break its long-term trend.", "level": round(level, 2), "turns": "sell"})
    due = ((stock or {}).get("results") or {}).get("next_on")
    if due:
        out.append({"text": f"Results are due on {date.fromisoformat(due):%d %b}; the call can change then."})
    if call and call.get("stop") and STANCE.get(call.get("action") or call.get("section")) in ("buy", "hold"):
        out.append({"text": f"A fall to ₹{call['stop']:,.0f} would be a sell.", "level": call["stop"], "turns": "sell"})
    return out[:MAX_CHANGE]


def _headline(call, up, down) -> str:
    text = (call.get("summary") or _reasons(call).get("summary")) if call else None
    if isinstance(text, str) and text.strip():
        return text.strip()
    if up or down:
        best = (up or down)[0]["text"]
        lead = "Best point for it" if up else "Main worry"
        return f"No call from us on this one yet. {lead}: {best[:1].lower() + best[1:]}."
    return "Nothing stands out for or against it yet."


def build(symbol: str, *, candidate: dict | None = None, sector: dict | None = None, stock: dict | None = None,
          call: dict | None = None, track: dict | None = None, trigger: str | None = None, as_of: str = "") -> dict | None:
    """The object for one stock, or None when there is nothing to say about it. `call` is the stored call row (probability,
    base_rate, base_rate_n, hurdle, entry/stop/target, would_buy_if, level_flag, change_reason, summary, action, `reasons`
    with `moved_by`, `for`, `against`); `candidate` is the screen's row; `stock` the stock file; `track` the call history;
    `trigger` the Ideas near-miss line."""
    facts = _facts(stock)
    code_for, code_against = _code_items(candidate, sector) if candidate else ([], [])
    an_for, an_against = _analyst_items(call) if call else ([], [])
    if not (candidate or call or facts):
        return None
    up, down = _merge(an_for, code_for, as_of), _merge(an_against, code_against, as_of)
    stance = "none"
    if call:
        stance = STANCE.get(call.get("action") or call.get("section") or "", "none")
        if stance == "sell" and _reasons(call).get("sell_kind", call.get("sell_kind")) == "weak":
            stance = "weak"
    r: dict = {"v": 1, "horizon": "about 3 months", "stance": stance, "headline": _headline(call, up, down)}
    for k, v in (("for", up), ("against", down), ("facts", facts)):
        if v:
            r[k] = v
    chance = _chance(call, up, down) if call else None
    if chance:
        r["chance"] = chance
        if chance.get("n") is None or chance["n"] < THIN_N:
            r["evidence_note"] = "limited evidence"
    levels = _levels(call) if call else None
    if levels:
        r["levels"] = levels
    view = _change_view(call, candidate, stock, trigger)
    if view:
        r["change_view"] = view
    if track or call:
        t = dict(track or {})
        if call and call.get("change_reason"):
            t["change_reason"] = call["change_reason"]
        else:
            t.setdefault("change_reason", None)
        if len(t) > 1 or t.get("change_reason"):
            r["track"] = t
    return r


class Book:
    """Everything `build` needs for every stock, read once for a site build: the stored calls of the newest run, the call
    history for `track`, the screen's sectors. `object(symbol)` is cached, so the tabs and the stock file show one object."""

    def __init__(self, db, day, result: dict, triggers: dict[str, str] | None = None):
        import json
        import statistics
        self.day, self.triggers, self.cache = str(result.get("as_of") or day), triggers or {}, {}
        self.candidates = {c["symbol"]: c for c in result["candidates"]}
        pes: dict = {}
        for c in result["candidates"]:
            pe = (c["metrics"] or {}).get("pe")
            if not c["flags"] and c["industry"] and pe and pe > 0:
                pes.setdefault(c["industry"], []).append(pe)
        self.sectors = {k: {"pe": statistics.median(v), "n": len(v)} for k, v in pes.items()}
        made = db.execute("select max(made_on) from calls where made_on <= ?", [day]).fetchone()[0]
        self.calls: dict[str, dict] = {}
        self.track: dict[str, dict] = {}
        if not made:
            return
        cur = db.execute("select * from calls where made_on = ? qualify row_number() over (partition by symbol order by id desc) = 1", [made])
        cols = [c[0] for c in cur.description]
        for row in cur.fetchall():
            c = dict(zip(cols, row))
            c["reasons"] = json.loads(c["reasons"]) if isinstance(c["reasons"], str) else c["reasons"] or {}
            self.calls[c["symbol"]] = c
        seen = {s: (first, n) for s, first, n in db.execute(
            "select symbol, min(made_on), count(distinct made_on) from calls where made_on <= ? group by symbol", [made]).fetchall()}
        before = dict(db.execute("select symbol, arg_max(probability, made_on) from calls where made_on < ? group by symbol", [made]).fetchall())
        for s in self.calls:
            first, n = seen[s]
            t = {"first_seen": str(first), "calls_made": n}
            if before.get(s) is not None:
                t["previous_p"] = round(before[s], 4)
            self.track[s] = t

    def object(self, symbol: str, stock: dict | None = None) -> dict | None:
        if stock is None and symbol in self.cache:
            return self.cache[symbol]
        c = self.candidates.get(symbol)
        obj = build(symbol, candidate=c, sector=self.sectors.get((c or {}).get("industry")), stock=stock,
                    call=self.calls.get(symbol), track=self.track.get(symbol), trigger=self.triggers.get(symbol), as_of=self.day)
        if stock is not None or symbol not in self.cache:
            self.cache[symbol] = obj
        return obj


def contract_errors(r: dict) -> list[str]:
    """What breaks the contract in one object (the check `sp verify` runs on every file that carries one)."""
    if "v" not in r:
        return ["missing v"]
    out = []
    if r.get("stance") not in ("buy", "hold", "watch", "weak", "sell", "none"):
        out.append(f"stance {r.get('stance')!r} is not one of buy, hold, watch, weak, sell, none")
    for side in ("for", "against"):
        items = r.get(side) or []
        if len(items) > MAX_SIDE:
            out.append(f"{side}: more than {MAX_SIDE} items")
        for i in items:
            if i.get("area") not in AREAS:
                out.append(f"{side}: area {i.get('area')!r} is unknown")
            if i.get("by") not in ("analyst", "code"):
                out.append(f"{side}: by {i.get('by')!r} is not analyst or code")
            if not i.get("text"):
                out.append(f"{side}: empty text")
    for f in r.get("facts") or []:
        if f.get("area") not in AREAS:
            out.append(f"facts: area {f.get('area')!r} is unknown")
    c = r.get("chance")
    if c is not None and not (0 <= c.get("p", -1) <= 1):
        out.append("chance.p is outside 0 to 1")
    if c is not None and (c.get("n") is None or c["n"] < THIN_N) and r.get("evidence_note") != "limited evidence":
        out.append("chance rests on fewer than 30 cases but evidence_note is missing")
    return out
