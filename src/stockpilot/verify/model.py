"""Checks 7 to 11: the forecast is robust, not only well worded. They read the newest day's calls from the store."""
import hashlib
import json
import re
from datetime import date
from pathlib import Path

from stockpilot import forecast
from stockpilot.analysis import screen
from stockpilot.calls.decide import Rules
from stockpilot.book import positions
from stockpilot.verify import FAIL, Gap, Result, reasoning_site

MIN_CHANCE, MAX_CHANCE, MIN_N = 0.05, 0.95, 30
CALIBRATION_MOVE = 0.08           # points of hit rate a bucket may move before the call must say "limited evidence"
LIMITED = "limited evidence"
FLIP_LIMIT, FLIP_MIN_SELLS = 0.40, 5
SPOT_CHECKS = 10


def _calls(db, day: date, with_section: bool = True):
    """The newest day's calls (latest per symbol), as dicts with the reasons json opened."""
    made = db.execute("select max(made_on) from calls where made_on <= ?" + (" and section is not null" if with_section else ""), [day]).fetchone()[0]
    if made is None:
        return None, []
    cur = db.execute("select * from calls where made_on = ?" + (" and section is not null" if with_section else "")
                     + " qualify row_number() over (partition by symbol order by id desc) = 1 order by symbol", [made])
    cols = [c[0] for c in cur.description]
    rows = []
    for x in cur.fetchall():
        row = dict(zip(cols, x))
        for k in ("reasons", "risks", "news", "warnings"):
            if isinstance(row.get(k), str):
                row[k] = json.loads(row[k])
        row["reasons"] = row.get("reasons") or {}
        rows.append(row)
    return made, rows


def _sell_kind(row) -> str | None:
    """sell, weak or review for a sell or trim call; a call stored before lane E has none, so a trim reads sell and a sell reads weak."""
    if row.get("section") not in ("sell", "trim"):
        return None
    kind = row["reasons"].get("sell_kind")
    return kind if kind in ("sell", "weak", "review") else ("sell" if row["section"] == "trim" else "weak")


# ---- 7: bounds and determinism -----------------------------------------------------------------------------

def _canonical(node) -> str:
    """The screen's output as text, floats cut to 9 significant digits: DuckDB adds numbers in a different order on each run, which
    moves the 16th digit and nothing a call is built on."""
    def tidy(x):
        if isinstance(x, float):
            return float(f"{x:.9g}")
        if isinstance(x, dict):
            return {k: tidy(v) for k, v in x.items()}
        if isinstance(x, list):
            return [tidy(v) for v in x]
        return x
    return json.dumps(tidy(node), default=str, sort_keys=True)


def check_site_evidence(ctx) -> Result:
    """The site part of check 7: a base rate on fewer than 30 cases (0 included) says "limited evidence" in its reasoning object."""
    r = Result(7, "Bounds and determinism")
    if ctx.site and (Path(ctx.site) / "data").is_dir():
        r.fail(*reasoning_site.evidence_problems(ctx.site))
    return r


def check_bounds(ctx) -> Result:
    r = Result(7, "Bounds and determinism")
    r.fail(*check_site_evidence(ctx).problems)
    made, rows = _calls(ctx.db, ctx.day)
    if made is None:
        return r.fail("there are no calls to check")
    for c in rows:
        s, p = c["symbol"], c["probability"]
        if p is None or not MIN_CHANCE <= p <= MAX_CHANCE:
            r.fail(f"{s}: chance {p} is outside {MIN_CHANCE:.0%} to {MAX_CHANCE:.0%}")
        # A holding with no usable history (a new listing, or too few cases) still gets a call; it must say "limited evidence".
        says_limited = c.get("kind") == "holding" and LIMITED in (c["reasons"].get("summary") or "").lower()
        if c["base_rate"] is None and not says_limited:
            r.fail(f"{s}: the call has no base rate")
        if (c.get("base_rate_n") or 0) < MIN_N and not says_limited:
            held = c.get("kind") == "holding"
            r.fail(f"{s}: its base rate rests on {c.get('base_rate_n') or 0} cases, fewer than {MIN_N}"
                   + (f", and the call text does not say \"{LIMITED}\"" if held else ""))
        if not c.get("horizon_days") or c["horizon_days"] <= 0:
            r.fail(f"{s}: the call states no horizon")
    first = _canonical(screen._compute(ctx.db, ctx.day, ctx.liquidity_floor_cr, screen.WEIGHTS))
    second = _canonical(screen._compute(ctx.db, ctx.day, ctx.liquidity_floor_cr, screen.WEIGHTS))
    if first != second:
        r.fail("the code screen gave different output on two runs with the same inputs")
    r.numbers = {"calls": len(rows), "calls_on": str(made), "screen_bytes": len(first), "deterministic": first == second}
    r.summary = (f"{len(rows)} calls of {made}: chances within {MIN_CHANCE:.0%} to {MAX_CHANCE:.0%}, each with a base rate (n at least {MIN_N}) and a horizon; "
                 + ("the screen is deterministic." if first == second else "the screen is NOT deterministic."))
    return r


# ---- 8: calibration ----------------------------------------------------------------------------------------

BUCKET_ROW = re.compile(r"^\|\s*(\d)\s*\|\s*(nifty_up|nifty_down)\s*\|\s*(calm|jumpy)\s*\|\s*(large|small)\s*\|\s*([\d,]+)\s*\|\s*([\d.]+)%")


def baseline_buckets(path: Path) -> dict:
    """{(momentum, regime, vol, liquidity): (n, hit_rate)} from the 40-bucket table in docs/backtest.md (the run the owners approved)."""
    out = {}
    for line in Path(path).read_text().splitlines():
        m = BUCKET_ROW.match(line)
        if m:
            out[(int(m[1]), m[2], m[3], m[4])] = (int(m[5].replace(",", "")), float(m[6]) / 100)
    return out


def current_buckets(db, ctx) -> tuple[dict, str]:
    """The buckets the calls use (base_rate_buckets), or a fresh backtest on the latest data when the check is asked to re-run it."""
    if ctx.run_backtest:
        from datetime import timedelta
        from stockpilot.analysis import backtest
        last = db.execute("select max(date) from prices").fetchone()[0]
        rates = backtest.base_rates(db, date(2016, 1, 1), last - timedelta(days=91))
        return {k: (v["n"], v["hit_rate"]) for k, v in rates.items()}, "re-run on the latest prices"
    rows = db.execute("select momentum, regime, vol, liquidity, n, hit_rate, max(computed_on) over () from base_rate_buckets where horizon_days = 91").fetchall()
    return {(m, r, v, l): (n, h) for m, r, v, l, n, h, _ in rows}, f"stored on {rows[0][6]}" if rows else "none stored"


def check_calibration(ctx) -> Result:
    r = Result(8, "Calibration: backtest buckets have not drifted", hard=False)
    baseline_file = Path(ctx.root) / "docs" / "backtest.md"
    if not baseline_file.exists():
        return r.fail("docs/backtest.md is missing, so there is no baseline to compare with")
    baseline = baseline_buckets(baseline_file)
    now, how = current_buckets(ctx.db, ctx)
    if not baseline:
        return r.fail("docs/backtest.md has no 40-bucket table")
    if not now:
        return r.fail("no backtest buckets are stored, so the base rates behind the calls cannot be checked")
    moved, thin = [], []
    for key, (n0, h0) in sorted(baseline.items()):
        if key not in now:
            thin.append(key)
            r.fail(f"bucket {key}: in the baseline but missing now")
            continue
        n1, h1 = now[key]
        if n1 < MIN_N:
            thin.append(key)
            r.fail(f"bucket {key}: only {n1} cases now (fewer than {MIN_N})")
        if abs(h1 - h0) > CALIBRATION_MOVE:
            moved.append(key)
            r.fail(f"bucket {key}: hit rate moved {100 * (h1 - h0):+.1f} points ({h0:.1%} to {h1:.1%})")
    watch = set(moved) | set(thin)
    unsafe = _bucket_calls(ctx, now, watch)
    for symbol in unsafe:
        r.fail(f"{symbol}: its base rate comes from a bucket that moved, is thin, or has no cases behind it, but the call text does not say \"{LIMITED}\"")
    r.numbers = {"buckets": len(baseline), "moved_over_8_points": len(moved), "thin_under_30": len(thin), "source": how,
                 "calls_missing_limited_evidence": len(unsafe)}
    r.summary = f"{len(baseline)} buckets ({how}) against docs/backtest.md: {len(moved)} moved over 8 points, {len(thin)} thin."
    return r


def _bucket_calls(ctx, now: dict, watch: set) -> list[str]:
    """Symbols whose call rests on a watched bucket (matched on base rate and n) and whose text lacks "limited evidence"."""
    _, rows = _calls(ctx.db, ctx.day)
    index = {(round(h, 3), n): key for key, (n, h) in now.items()}
    out = []
    for c in rows:
        key = index.get((round(c["base_rate"] or -1, 3), c.get("base_rate_n")))
        thin = (c.get("base_rate_n") or 0) < MIN_N
        if (key in watch or thin) and LIMITED not in (c["reasons"].get("summary") or "").lower():
            out.append(c["symbol"])
    return out


# ---- 9: rule guards ----------------------------------------------------------------------------------------

def check_rule_guards(ctx) -> Result:
    r = Result(9, "Rule guards: Sell, Buy and number consistency")
    db, rules = ctx.db, ctx.rules or Rules()
    made, rows = _calls(db, ctx.day)
    if made is None:
        return r.fail("there are no calls to check")
    held = {p.symbol: p for p in positions.held(db, ctx.day)}
    for c in rows:
        s, section, kind = c["symbol"], c["section"], _sell_kind(c)
        p = held.get(s)
        price = (p.price if p and p.price else None) or c.get("entry")
        value = (p.quantity * price) if p and price else None
        if section in ("sell", "trim"):
            if value is not None and value < rules.min_sale_inr:
                r.fail(f"{s}: a {section} call on a holding worth ₹{value:,.0f}, under ₹{rules.min_sale_inr:,.0f}")
            if rules.is_passive(s) and section == "sell" and kind != "sell":
                r.fail(f"{s}: a Sell for a passive fund on a low chance ({c['probability']:.0%})")
            if section == "sell" and kind == "sell":
                stop_hit = bool(c.get("stop") and price and price <= c["stop"])
                if not (stop_hit or (c["reasons"].get("broken_reason") or "").strip()):
                    r.fail(f"{s}: a Sell with no sell price reached and no broken reason (one weak quarter alone?)")
            if kind == "review" and section == "sell" and False:
                pass
        entry, stop, target = c.get("entry"), c.get("stop"), c.get("target")
        if stop and target and target <= stop:
            r.fail(f"{s}: its target {target:g} is not above its stop {stop:g}")
        if section != "sell" and section != "trim" and entry and stop and stop >= entry:
            r.fail(f"{s}: its stop {stop:g} is not below its price {entry:g}")
        if section == "buy" and entry and target and target <= entry:
            r.fail(f"{s}: a Buy whose target {target:g} is not above its price {entry:g}")
    buys = [c for c in rows if c["section"] == "buy"]
    spend = sum(c.get("size_inr") or 0 for c in buys)
    left = forecast.budget_left(db, ctx.day, ctx.budget_default)
    if spend > left + 1:
        r.fail(f"the Buy calls add up to ₹{spend:,.0f}, more than the ₹{left:,.0f} left in this month's budget")
    r.numbers = {"calls": len(rows), "sells": sum(c["section"] in ("sell", "trim") for c in rows), "buys": len(buys),
                 "buy_spend_inr": round(spend), "budget_left_inr": round(left)}
    r.summary = f"{len(rows)} calls checked ({r.numbers['sells']} sells, {len(buys)} buys, ₹{spend:,.0f} against ₹{left:,.0f} left)."
    return r


# ---- 10: model sanity --------------------------------------------------------------------------------------

NUMBER = re.compile(r"(₹\s?)?(\d[\d,]*(?:\.\d+)?)\s?(%|x|×|crore|cr|lakh)?")
SPOT_FIELDS = ("summary", "would_buy_if", "change_reason")


def _flatten(node, out: list):
    if isinstance(node, bool):
        return
    if isinstance(node, (int, float)):
        out.append(float(node))
    elif isinstance(node, str):
        for m in NUMBER.finditer(node):
            try:
                out.append(float(m[2].replace(",", "")))
            except ValueError:
                pass
    elif isinstance(node, dict):
        for v in node.values():
            _flatten(v, out)
    elif isinstance(node, list):
        for v in node:
            _flatten(v, out)


def brief_numbers(entry: dict, market: dict) -> list[float]:
    out: list[float] = []
    _flatten(entry, out)
    _flatten(market, out)
    return out


def number_in_brief(n: float, unit: str, values: list[float]) -> bool:
    """`n` (as written, with its unit) is a number in the brief, or a simple difference, percent change or ratio of two of them."""
    pct = unit == "%"
    tol = 0.6 if pct else max(0.006 * abs(n), 0.51 if unit in ("", "₹") else 0.06)
    scaled = [v * 100 for v in values] if pct else []
    pool = values + scaled
    if any(abs(v - n) <= tol for v in pool):
        return True
    near = [v for v in values if v]
    near = near[:150]
    for i, a in enumerate(near):
        for b in near[i + 1:]:
            if abs(abs(a - b) - n) <= tol:
                return True
            if pct and (abs(100 * (a / b - 1) - n) <= tol or abs(100 * (b / a - 1) - n) <= tol or abs(100 * abs(a - b) / max(abs(a), abs(b)) - n) <= tol):
                return True
            if unit in ("x", "×") and (abs(a / b - n) <= tol or abs(b / a - n) <= tol):
                return True
    return False


def _tokens(text: str):
    for m in NUMBER.finditer(text or ""):
        unit = "₹" if m[1] else (m[3] or "")
        value = float(m[2].replace(",", ""))
        has_unit = bool(m[1] or m[3])
        if not has_unit and "." not in m[2] and value < 100:       # "3 months", "2 quarters": counting words, not figures
            continue
        yield value, ("x" if unit == "×" else "cr" if unit in ("crore", "cr") else unit), m[0].strip()


def check_site_numbers(ctx) -> Result:
    """The site part of check 10: every number in an analyst sentence on the stock files traces to the stock's data or its brief."""
    r = Result(10, "Model sanity: numbers match the brief, evidence is cited")
    if not (ctx.site and (Path(ctx.site) / "data").is_dir()):
        return r
    problems, sentences = reasoning_site.trace_problems(ctx.site, _brief_reader(ctx))
    r.fail(*problems[:40])
    r.numbers = {"analyst_sentences": sentences, "sentences_with_untraced_numbers": len(problems)}
    return r


def _brief_reader(ctx):
    """stock -> its entry in the newest kept brief that holds it, or None when no brief was kept (or none holds it)."""
    files = sorted(Path(ctx.briefs).glob("*.json"), reverse=True) if ctx.briefs and Path(ctx.briefs).is_dir() else []
    loaded: dict[Path, dict] = {}

    def entry(symbol):
        for f in files:
            if f not in loaded:
                try:
                    loaded[f] = {e["symbol"]: e for e in json.loads(f.read_text()).get("stocks", []) if isinstance(e, dict) and "symbol" in e}
                except (ValueError, OSError):
                    loaded[f] = {}
            if symbol in loaded[f]:
                return loaded[f][symbol]
        return None
    return entry


def check_analyst_numbers(ctx) -> Result:
    r = Result(10, "Model sanity: numbers match the brief, evidence is cited")
    r.fail(*check_site_numbers(ctx).problems)
    made, rows = _calls(ctx.db, ctx.day, with_section=False)
    if made is None:
        return r.fail("there are no calls to check")
    brief = Path(ctx.briefs) / f"{made}.json" if ctx.briefs else None
    if not brief or not brief.exists():
        return r.fail(f"the brief the analyst saw on {made} was not kept ({brief or 'no briefs folder given'}), so its numbers cannot be checked")
    body = json.loads(brief.read_text())
    entries = {e["symbol"]: e for e in body.get("stocks", [])}
    pool = []
    for c in rows:
        e = entries.get(c["symbol"])
        if e is None:
            continue
        texts = [(f, c["reasons"].get(f) if f == "summary" else c.get(f)) for f in SPOT_FIELDS]
        texts += [("moved_by", m.get("reason")) for m in c["reasons"].get("moved_by") or []]
        for field, text in texts:
            for value, unit, raw in _tokens(text or ""):
                pool.append((hashlib.sha1(f"{made}|{c['symbol']}|{field}|{raw}".encode()).hexdigest(), c["symbol"], field, value, unit, raw))
    pool.sort()
    checked, wrong = pool[:SPOT_CHECKS], []
    cache: dict[str, list[float]] = {}
    for _, symbol, field, value, unit, raw in checked:
        values = cache.setdefault(symbol, brief_numbers(entries[symbol], body.get("market") or {}))
        if not number_in_brief(value, unit, values):
            wrong.append(f"{symbol} ({field}): the analyst wrote \"{raw}\" and no such number is in its brief")
    r.fail(*wrong)
    unevidenced = []
    for c in rows:
        if c["symbol"] not in entries or c.get("probability") is None or c.get("base_rate") is None:
            continue
        moved = abs(c["probability"] - c["base_rate"]) >= 0.03
        cited = bool(c["reasons"].get("moved_by")) or bool(c.get("news"))
        if moved and not cited:
            unevidenced.append(c["symbol"])
            r.fail(f"{c['symbol']}: its chance sits {100 * (c['probability'] - c['base_rate']):+.0f} points from the base rate with no evidence cited; the code-only call should stand")
    r.numbers = {"calls_on": str(made), "numbers_found": len(pool), "spot_checked": len(checked), "not_in_brief": len(wrong),
                 "without_evidence": len(unevidenced)}
    r.summary = f"{len(checked)} of {len(pool)} cited numbers spot-checked against the brief: {len(wrong)} not found; {len(unevidenced)} moved calls cite no evidence."
    return r


# ---- 11: regression ----------------------------------------------------------------------------------------

def check_regression(ctx) -> Result:
    r = Result(11, "Regression: Sells do not flip run to run", hard=False)
    db = ctx.db
    made, today = _calls(db, ctx.day)
    if made is None:
        return r.fail("there are no calls to compare")
    prev = db.execute("select max(made_on) from calls where made_on < ? and section is not null", [made]).fetchone()[0]
    if prev is None:
        r.summary = "This is the first set of calls; nothing to compare with."
        r.numbers = {"calls_on": str(made), "previous_on": None}
        return r
    _, before = _calls(db, prev)
    t = {c["symbol"]: c["section"] in ("sell", "trim") for c in today}
    b = {c["symbol"]: c["section"] in ("sell", "trim") for c in before}
    both = set(t) & set(b)
    union = {s for s in both if t[s] or b[s]}
    flipped = sorted(s for s in union if t[s] != b[s])
    rate = len(flipped) / len(union) if union else 0.0
    r.numbers = {"calls_on": str(made), "previous_on": str(prev), "sells_in_either": len(union), "flipped": len(flipped), "flip_rate": round(rate, 3)}
    if len(union) >= FLIP_MIN_SELLS and rate > FLIP_LIMIT:
        r.fail(f"{len(flipped)} of {len(union)} Sells flipped between {prev} and {made} ({rate:.0%}): {', '.join(flipped[:10])}")
    r.summary = f"{len(flipped)} of {len(union)} Sells flipped since {prev} ({rate:.0%}; the limit is {FLIP_LIMIT:.0%} once there are {FLIP_MIN_SELLS} or more)."
    return r
