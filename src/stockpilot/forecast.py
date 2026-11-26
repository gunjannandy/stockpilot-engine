"""The evening forecast: pick the stocks worth a look, build their dossiers, ask the model for chances, and let code turn
the chances into calls. `run` is the whole of `daily_decide`; `site_payload` is what the dashboard's new calls.json shows.

Order: archive guard -> screen and holdings -> holding checks -> universe -> headlines -> readiness -> dossiers, levels,
hurdles -> analyst (and a second call on Saturday) -> skeptic on borderline stocks -> decide -> calls rows."""
import importlib
import json
import zlib
from datetime import date, timedelta

from stockpilot import costs, dossier, house_rules, journal, learn, levels, readiness, reasoning

from stockpilot.analysis import analytics, held_base_rate, screen

from stockpilot.calls import bn, brief as brief_mod, decide, runner

from stockpilot.sources import exchange
from stockpilot.verify import flags
from stockpilot.calls import record as track_record
from stockpilot.book import budget as book_budget, positions, record
from stockpilot.calls.decide import Rules

PROVEN_AFTER = 30         # calls stay "unproven" until this many have been scored
TOP_SCREEN = 25
RESULTS_WITHIN_DAYS = 10
NEAR_200DMA = 0.01
STRONG_MOMENTUM = 0.8
LONG_TERM_SOON_DAYS = 30
UNEVIDENCED_MOVE = 0.03      # points of chance the model may move from the base rate without citing a reason or news (verify check 10 uses the same)
THREE_MONTHS = 63


# ---- small reads -------------------------------------------------------------------------------------------

def day_archived(db, day: date) -> bool:
    return bool(db.execute("select count(*) from archived_days where day = ?", [day]).fetchone()[0])


def active_not_now(db, day: date) -> list[tuple[str, str]]:
    return db.execute("select symbol, scope from not_now where undone_at is null and (until is null or until >= ?)",
                      [day]).fetchall()


def _setasides(db, day: date, rules: Rules) -> dict[str, int]:
    rows = db.execute("select s.industry, count(*) from not_now n join stocks s using (symbol) "
                      "where n.undone_at is null and n.scope in ('buy', 'any') and n.set_at >= ? and s.industry is not null "
                      "group by s.industry", [day - timedelta(days=rules.setaside_days)]).fetchall()
    return {industry: n for industry, n in rows}


def _recent_sector_buys(db, day: date, rules: Rules) -> dict[str, set]:
    out: dict[str, set] = {}
    for industry, symbol in db.execute(
            "select s.industry, c.symbol from calls c join stocks s using (symbol) where c.made_on < ? and c.made_on >= ? "
            "and coalesce(c.section, case when c.action in ('buy', 'add') then 'buy' end) = 'buy' and s.industry is not null",
            [day, day - timedelta(days=rules.sector_week_days)]).fetchall():
        out.setdefault(industry, set()).add(symbol)
    return out


def _call_history(db, symbols: list[str], day: date) -> tuple[dict, dict]:
    """(previous section by symbol, first day of the current run of buy calls by symbol)."""
    previous, since = {}, {}
    if not symbols:
        return previous, since
    rows = db.execute(
        "select symbol, made_on, coalesce(section, case when action in ('buy', 'add') then 'buy' else action end) from calls "
        "where made_on < ? and list_contains(?, symbol) "
        "qualify row_number() over (partition by symbol, made_on order by id desc) = 1 order by symbol, made_on desc",
        [day, symbols]).fetchall()
    run_open: dict[str, bool] = {}
    for symbol, made_on, section in rows:
        if symbol not in previous:
            previous[symbol] = section
            run_open[symbol] = True
        if run_open.get(symbol):
            if section == "buy":
                since[symbol] = made_on
            else:
                run_open[symbol] = False
    return previous, since


def _trading_days_before(db, day: date, n: int) -> date:
    d, left = day, n
    while left:
        d -= timedelta(days=1)
        if exchange.is_trading_day(db, d):
            left -= 1
    return d


def budget_left(db, day: date, budget_inr: float) -> float:
    """The month's budget less buys detected this month: a call is acted on when R5's detection sets `acted_on`. Until
    that exists, the full budget is left."""
    month = day.strftime("%Y-%m")
    spent = db.execute("select coalesce(sum(size_inr), 0) from calls where acted_on is not null "
                       "and strftime(acted_on, '%Y-%m') = ? and coalesce(section, action) in ('buy', 'add')", [month]).fetchone()[0]
    return book_budget.for_month(db, day, budget_inr) - spent


# ---- holding checks ----------------------------------------------------------------------------------------

def _returns_3m(db, symbols: list[str], day: date) -> dict[str, float]:
    if not symbols:
        return {}
    sql = analytics.ADJUSTED_SQL.format(symbol_filter="and list_contains($syms, symbol) and exchange = 'NSE'")
    rows = db.execute(f"select symbol, adj_close from ({sql}) where date <= $day order by symbol, date",
                      {"since": day - timedelta(days=140), "syms": symbols, "day": day}).fetchall()
    series: dict[str, list[float]] = {}
    for symbol, close in rows:
        series.setdefault(symbol, []).append(close)
    return {s: v[-1] / v[-THREE_MONTHS - 1] - 1 for s, v in series.items() if len(v) > THREE_MONTHS}


def _opened_from_call(db, p: positions.Position, day: date, rules: Rules) -> dict | None:
    """The call a position was opened from: its earliest open lot is on or after `stops_from` and a buy call on the stock
    was made within `stop_call_days` trading days before that lot. Older holdings never qualify."""
    fresh = sorted(l.acquired_on for l in p.lots)
    if not fresh or fresh[0] < rules.stops_from:
        return None
    opened = fresh[0]
    row = db.execute(
        "select stop, target, made_on from calls where symbol = ? and made_on <= ? and made_on >= ? "
        "and coalesce(section, case when action in ('buy', 'add') then 'buy' end) = 'buy' and stop is not null "
        "order by made_on desc, id desc limit 1",
        [p.symbol, opened, _trading_days_before(db, opened, rules.stop_call_days)]).fetchone()
    return {"stop": row[0], "target": row[1], "called_on": row[2]} if row else None


def _results_miss(db, symbol: str, day: date, rules: Rules) -> str | None:
    """The latest filed quarter's net profit against the same quarter a year earlier: down `rules.results_miss` or more.
    A loss a year ago has no percentage to fall by, so it is never a miss; a swing from profit to loss is."""
    if not readiness.has_table(db, "quarterly"):
        return None
    from stockpilot.sources import filings
    rows = filings.history(db, symbol, day, 8)
    if not rows or rows[0]["net_profit"] is None:
        return None
    latest = rows[0]
    year_ago = dossier.year_ago(rows)
    if not year_ago or year_ago["net_profit"] is None or year_ago["net_profit"] <= 0:
        return None
    fall = 1 - latest["net_profit"] / year_ago["net_profit"]
    if fall < rules.results_miss - 1e-9:
        return None
    return f"profit for the quarter to {latest['period_end']:%b %Y} fell {100 * fall:.0f}% on a year earlier"


def holding_checks(db, day: date, held: list[positions.Position], rules: Rules, portfolio_value: float,
                   sector_returns: dict) -> dict[str, dict]:
    """Every equity holding, every evening: ASM/GSM flag; 20 points behind its sector over three months; above the
    single-stock cap; a lot turning long-term within 30 days; a stop or target reached on a position opened from a call.
    The ASM/GSM flag, the sector gap and a results miss (latest quarter's net profit down 25% or more on the same quarter a
    year earlier, from `filings.history`) are also thesis breaks: `decide` sells on them.
    Returns symbol -> {"triggers": [plain sentences], "thesis_break": [plain sentences], "stop_hit": the stop or None}."""
    equity = [p for p in held if p.kind == "equity" and p.quantity > 0]
    flagged = dict(db.execute("select symbol, label from surveillance where as_of = "
                              "(select max(as_of) from surveillance where as_of <= ?)", [day]).fetchall())
    industry = dict(db.execute("select symbol, industry from stocks").fetchall())
    returns = _returns_3m(db, [p.symbol for p in equity], day)
    out = {}
    for p in equity:
        triggers, broke, stop_hit = [], [], None
        if p.symbol in flagged:
            broke.append(f"on the exchange's watch list ({flagged[p.symbol]})")
        sector = sector_returns.get(rules.sector_index.get(industry.get(p.symbol)))
        if sector is not None and p.symbol in returns and returns[p.symbol] - sector <= -rules.behind_sector:
            broke.append(f"{abs(100 * (returns[p.symbol] - sector)):.0f} points behind its sector over 3 months")
        if miss := _results_miss(db, p.symbol, day, rules):
            broke.append(miss)
        triggers += broke
        if portfolio_value > 0 and p.value / portfolio_value > rules.max_single:
            triggers.append(f"{100 * p.value / portfolio_value:.1f}% of the portfolio (limit {rules.max_single:.0%})")
        soon = [l.turns_long_term_on for l in p.lots if l.turns_long_term_on and day < l.turns_long_term_on
                <= day + timedelta(days=LONG_TERM_SOON_DAYS)]
        if soon:
            triggers.append(f"a lot turns long-term on {min(soon):%d %b}")
        origin = _opened_from_call(db, p, day, rules)
        if origin and p.price:
            if origin["stop"] and p.price <= origin["stop"]:
                stop_hit = origin["stop"]
                triggers.append(f"reached its stop of ₹{origin['stop']:,.0f}")
            elif origin["target"] and p.price >= origin["target"]:
                triggers.append(f"reached its target of ₹{origin['target']:,.0f}")
        if triggers or stop_hit:
            out[p.symbol] = {"triggers": triggers, "thesis_break": broke, "stop_hit": stop_hit}
    return out


# ---- the universe ------------------------------------------------------------------------------------------

def _rotating(p: positions.Position, day: date) -> bool:
    """A stable fifth of the other holdings each evening (hash() changes every run, crc32 does not)."""
    return zlib.crc32((p.isin or p.symbol).encode()) % 5 == day.toordinal() % 5


def pick_universe(db, day: date, result: dict, held: list[positions.Position], checks: dict, hidden_buy: set,
                  watch_cap: int = Rules.watch_cap) -> dict[str, list[str]]:
    """symbol -> why it is in tonight's brief. About 35 stocks: the screen's top 25, triggered watchlist stocks,
    triggered holdings, and a rotating fifth of the other holdings."""
    why: dict[str, list[str]] = {}
    mine = {p.symbol: p for p in held if p.kind == "equity" and p.quantity > 0}
    ranked = sorted((c for c in result["candidates"] if not c["flags"] and c["symbol"] not in hidden_buy),
                    key=lambda c: (-c["composite"], c["symbol"]))      # ties by name: a rerun must pick the same stocks
    for i, c in enumerate(ranked[:TOP_SCREEN]):
        why.setdefault(c["symbol"], []).append(f"screen rank {i + 1}")
    soon = set()
    if readiness.has_table(db, "results_calendar"):
        soon = {s for (s,) in db.execute("select distinct symbol from results_calendar where date >= ? and date <= ?",
                                         [day, day + timedelta(days=RESULTS_WITHIN_DAYS)]).fetchall()}
    triggered = []
    for c in result["candidates"]:
        if not c["watchlist"] or c["symbol"] in mine or c["symbol"] in hidden_buy:
            continue
        m, found = c["metrics"], []
        if c["symbol"] in soon:
            found.append("watchlist: results within 10 days")
        if m.get("dist_200dma") is not None and abs(m["dist_200dma"]) < NEAR_200DMA:
            found.append("watchlist: at its 200-day average")
        if c["scores"]["momentum"] >= STRONG_MOMENTUM:
            found.append("watchlist: strong momentum")
        if found:
            triggered.append((c["symbol"], found, c["composite"]))
    # Strong momentum alone is true of a fifth of any list, so the evening keeps the best few: a results date first,
    # then the 200-day average, then momentum, each by screen score.
    order = {"watchlist: results within 10 days": 0, "watchlist: at its 200-day average": 1, "watchlist: strong momentum": 2}
    triggered.sort(key=lambda t: (min(order[f] for f in t[1]), -t[2], t[0]))
    for symbol, found, _ in triggered[:watch_cap]:
        why.setdefault(symbol, []).extend(found)
    for symbol, p in mine.items():
        if symbol in checks:
            why.setdefault(symbol, []).extend("holding: " + t for t in checks[symbol]["triggers"])
        elif _rotating(p, day):
            why.setdefault(symbol, []).append("holding: this evening's rotating review")
    return why


# ---- the run -----------------------------------------------------------------------------------------------

def fit(brief: dict, limit: int | None = None) -> list[dict]:
    """The brief, or halves of it, each small enough for the runner's cap. A normal evening is one brief; a Saturday with
    many holdings may need a third call rather than a failed run."""
    limit = limit or runner.MAX_BRIEF_BYTES
    if len(json.dumps(brief, default=str, separators=(",", ":"))) <= limit * 0.95 or len(brief["stocks"]) < 2:
        return [brief]
    mid = len(brief["stocks"]) // 2
    return fit({**brief, "stocks": brief["stocks"][:mid]}, limit) + fit({**brief, "stocks": brief["stocks"][mid:]}, limit)


def run(db, day: date, analyse, runners: list[str], rules: Rules = Rules(), budget_inr: float = 0.0,
        liquidity_floor_cr: float = 1.0, *, brief_dir=None, full_review: bool | None = None, fetch=None) -> dict:
    """The evening forecast as one `daily_decide` run. Any exception ends the run failed with a problem row (and is
    returned, not raised, so the pipeline can finish). A day the archive already holds is frozen and refused."""
    try:
        with journal.run(db, "daily_decide") as r:
            return _run(db, r, day, analyse, runners, rules, budget_inr, liquidity_floor_cr, brief_dir,
                        day.weekday() == 5 if full_review is None else full_review, fetch)
    except Exception as err:  # noqa: BLE001 - journal.run has recorded it; the caller gets the failure
        return {"status": "failed", "error": str(err)}


def _run(db, r, day, analyse, runners, rules, budget_inr, floor, brief_dir, full_review, fetch) -> dict:
    if day_archived(db, day):
        r.status = "skipped"
        r.notes["note"] = f"The calls for {day} are already archived, so the day is frozen; nothing was changed."
        return {"status": "skipped", "note": r.notes["note"]}
    result = screen.run(db, day, floor)
    held = positions.held(db, day)
    pv = sum(p.value for p in held if p.kind == "equity")
    ctx = dossier.context(db, day, result, held, rules.sector_index)
    checks = holding_checks(db, day, held, rules, pv, ctx.sector_returns)
    not_now = active_not_now(db, day)
    hidden_buy = {s for s, sc in not_now if sc in ("buy", "any")}
    why = pick_universe(db, day, result, held, checks, hidden_buy, rules.watch_cap)
    for symbol in flags.flagged_symbols(db) & set(why):          # lane V: a price series with an unexplained jump is never analysed
        del why[symbol]
        r.warn(f"{symbol}: its price series has an unexplained jump, so it was left out of tonight's calls.", key=f"price-flag-{symbol}")
    mine = {p.symbol: p for p in held if p.kind == "equity" and p.quantity > 0}
    if full_review:
        for symbol in mine:
            why.setdefault(symbol, []).append("holding: Saturday's full review")
    names = dict(db.execute("select symbol, name from stocks").fetchall())
    if fetch:   # headlines come from lane R3's source; until it exists, or when a feed fails, that is a gap, not a failure
        try:
            headlines = importlib.import_module("stockpilot.sources.headlines")
        except ImportError:
            headlines = None
        if headlines:
            try:
                headlines.for_symbols(db, day, list(why), names, fetch)
            except Exception as err:  # noqa: BLE001
                r.warn(f"headlines: {err!r}", key="headlines")
    ready = readiness.check(db, day)
    block = " ".join(g for g in ready["gaps"] if "no buy calls" in g) if ready["block_buys"] else None

    entries, items_meta = [], {}
    own_factors = None
    for symbol, reasons in why.items():
        d = dossier.build(db, symbol, day, ctx=ctx)
        held_note = None
        if symbol in mine:     # lane P2: a holding's base rate never depends on what the screen dropped
            own_factors = own_factors or analytics.price_factors(db, day)
            on_screen = not held_base_rate.needs_own_history(symbol, ctx.candidates)
            held_note = held_base_rate.for_held(db, symbol, day, rates=ctx.rates, regime=ctx.regime, candidates=ctx.candidates,
                                                median_vol=ctx.median_vol, floor_cr=floor, factors=own_factors,
                                                screen_rate=d["base_rate"] if on_screen else None)
            if not on_screen:
                d["base_rate"] = {"rate": held_note["rate"], "n": held_note["n"]}
        lv = levels.for_stock(d)
        adv = (d.get("price") or {}).get("liquidity_cr")
        trade = rules.max_single * pv if pv > 0 else 100_000     # a full-size position: the flat depository fee weighs less on it
        hurdle = costs.hurdle_for(trade, adv, rules.nifty_3m) if lv else None
        entries.append(brief_mod.entry(d, reasons, lv, hurdle))
        items_meta[symbol] = {"dossier": d, "levels": lv, "hurdle": hurdle, "adv": adv, "held_note": held_note}
    market = dossier.market(db, day, ctx, [m["dossier"]["industry"] for m in items_meta.values()], list(mine))
    try:   # R8: two plain lines about the father's own trading; a fact about him, so the analyst can weigh it
        if lines := record.build(db, day)["lines"]:
            market = {**market, "about_you": list(lines)}
    except Exception as err:  # noqa: BLE001
        r.warn(f"own record: {err!r}", key="own_record")
    b = brief_mod.build(day, ctx.regime, market, ready["gaps"], entries, house_rules=house_rules.active(db),
                        review="saturday" if full_review else "daily")
    if brief_dir:   # kept so the archive can show exactly what the model was told
        from pathlib import Path
        Path(brief_dir).mkdir(parents=True, exist_ok=True)
        (Path(brief_dir) / f"{day}.json").write_text(json.dumps(b, default=str, indent=1))

    failures, answers, market_view, market_view_bn, runner_name = [], {}, "", "", None
    briefs = [b]
    if full_review:    # Saturday: every holding goes to a second call; the first keeps the other stocks
        others = [e for e in entries if e["symbol"] not in mine]
        owned = [e for e in entries if e["symbol"] in mine]
        briefs = [{**b, "stocks": part} for part in (others, owned) if part]
    briefs = [piece for part in briefs for piece in fit(part)]
    for part in briefs:
        got = analyse(part, "analyst", runners)
        runner_name = runner_name or got["runner"]
        failures += got["failures"]
        market_view = market_view or got["decisions"]["market_view"]
        market_view_bn = market_view_bn or got["decisions"].get("market_view_bn", "")
        wanted = {s["symbol"] for s in part["stocks"]}
        answers.update({i["symbol"]: i for i in got["decisions"]["items"] if i["symbol"] in wanted})

    bn_rejected = []                      # lane E: a _bn field that fails the code check is blanked, and the run says so
    for symbol, a in answers.items():
        a["summary_bn"], why = bn.clean(a["summary"], a.get("summary_bn"))
        bn_rejected += [f"{symbol} summary_bn: {w}" for w in why]
    market_view_bn, why = bn.clean(market_view, market_view_bn)
    bn_rejected += [f"market_view_bn: {w}" for w in why]
    dropped = []                          # lane F1: the analyst's for/against lines keep only numbers the brief holds
    entry_of = {e["symbol"]: e for e in entries}
    for symbol, a in answers.items():
        for side in ("for", "against"):
            a[side], why = reasoning.clean_analyst_items(a.get(side), entry_of.get(symbol, {}), side)
            dropped += [f"{symbol} {w}" for w in why]
        a["unknowns"] = [u.strip() for u in a.get("what_we_do_not_know") or [] if isinstance(u, str) and u.strip()][:5]
    previous, since = _call_history(db, list(answers), day)
    marked = {s for (s,) in db.execute("select symbol from long_term_marks").fetchall()}

    def item_for(symbol: str, a: dict) -> dict:
        meta, d = items_meta[symbol], items_meta[symbol]["dossier"]
        p = mine.get(symbol)
        return {"symbol": symbol, "name": d["name"], "industry": d["industry"], "probability": a["probability"],
                "kind": "holding" if p else "candidate", "held_qty": p.quantity if p else 0,
                "passive": bool(p) and rules.is_passive(symbol),
                "price": (p.price if p and p.price else (d.get("price") or {}).get("close")),
                "levels": meta["levels"], "adv_cr": meta["adv"], "hurdle": meta["hurdle"],
                "lots": [{"acquired_on": l.acquired_on, "quantity": l.quantity, "cost": l.cost,
                          "turns_long_term_on": l.turns_long_term_on} for l in (p.lots if p else [])],
                "stop_hit": (checks.get(symbol) or {}).get("stop_hit"), "long_term": symbol in marked,
                "broken_reason": a.get("broken_reason") if p else None, "buy_since": since.get(symbol),
                "base_rate": d["base_rate"]["rate"], "base_rate_n": d["base_rate"]["n"], "summary": _held_summary(a["summary"], meta["held_note"]),
                "summary_bn": a["summary_bn"], "moved_by": a["moved_by"], "risks": a["risks"], "news_used": a["news_used"],
                "level_flag": a["level_flag"], "change_reason": a["change_reason"], "would_buy_if": a["would_buy_if"] or "",
                "for": a["for"], "against": a["against"], "unknowns": a["unknowns"]}

    unevidenced = []                      # issue #17: a chance moved 3 points or more from the base rate with no reason and no news
    for symbol, a in answers.items():     # is the model's guess, not evidence: the code-only call (the base rate) stands
        rate = items_meta[symbol]["dossier"]["base_rate"]["rate"]
        if rate is not None and abs(a["probability"] - rate) >= UNEVIDENCED_MOVE and not a["moved_by"] and not a["news_used"]:
            a["probability"] = round(rate, 4)
            unevidenced.append(symbol)
    items = [item_for(s, a) for s, a in answers.items()]
    skeptic = {}
    calibrate = track_record.calibrator(db)       # identity until 30 calls are scored; the line is read on the calibrated chance
    near = decide.borderline([{**it, "probability": calibrate(it["probability"])} for it in items], rules)
    if near:
        try:
            second = analyse(brief_mod.for_skeptic(b, answers, near), "skeptic", runners)
            skeptic = {i["symbol"]: i for i in second["decisions"]["items"] if i["symbol"] in near}
            failures += second["failures"]
        except runner.RunnerError as err:   # the analyst's call stands; note the gap
            failures.append({"runner": "skeptic", "error": str(err)[:500]})
    for it in items:
        if it["symbol"] in skeptic:
            it["probability"] = round((it["probability"] + skeptic[it["symbol"]]["probability"]) / 2, 4)
        it["raw_probability"] = it["probability"]     # what the model said, stored and scored; code decides on the calibrated one
        it["probability"] = calibrate(it["probability"])

    sector_values: dict[str, float] = {}
    all_industry = dict(db.execute("select symbol, industry from stocks").fetchall())
    for p in mine.values():
        if all_industry.get(p.symbol):
            sector_values[all_industry[p.symbol]] = sector_values.get(all_industry[p.symbol], 0.0) + p.value
    found = learn.patterns(db, day, result)      # selection only: the model was never told, and a sell or trim ignores it
    feats = learn.features(result)
    for it in items:
        it["learned"] = learn.match(found, feats.get(it["symbol"]))
    decided = decide.sections(items, rules=rules, day=day, portfolio_value=pv, sector_values=sector_values, block_buys=block,
                              not_now=not_now, setasides=_setasides(db, day, rules),
                              recent_sector_buys=_recent_sector_buys(db, day, rules))
    calls = decided["calls"]
    missing_reason, jargon = [], []
    for c in calls:
        prev = previous.get(c["symbol"])
        if prev and prev != c["section"] and not (c["change_reason"] or "").strip():
            missing_reason.append(c["symbol"])
            c["change_reason"] = f"Was a {prev} call, now {c['section']}; its chance is {c['probability']:.0%}."
        for word in runner.jargon_in(" ".join(filter(None, [c["summary"], c["would_buy_if"], c["change_reason"]]))):
            jargon.append(f"{c['symbol']}: {word}")

    buys = [c for c in calls if c["section"] == "buy"]
    line = decide.budget_line(budget_left(db, day, budget_inr), [c["amount"] for c in buys])
    unproven = db.execute("select count(*) from calls where score_3m is not null").fetchone()[0] < PROVEN_AFTER
    _store(db, r.id, day, calls, b, rules, runner_name, skeptic, unproven)
    if bn_rejected:
        r.warn(f"{len(bn_rejected)} Bengali fields failed the check and were left blank (for example {bn_rejected[0]}).", key="bengali")
    if jargon:
        r.warn(f"The model used jargon in {len(jargon)} places (for example {', '.join(jargon[:3])}).", key="jargon")
    r.notes.update({"calls": len(calls), "market_view": market_view, "market_view_bn": market_view_bn, "gaps": ready["gaps"],
                    "block_buys": bool(block), "budget_line": line, "sector_notes": decided["sector_notes"],
                    "borderline": near, "runner": runner_name, "failures": failures, "full_review": full_review,
                    "universe": len(why), "checks": {s: v["triggers"] for s, v in checks.items()},
                    "missing_change_reason": missing_reason, "unevidenced_reset": unevidenced, "reasoning_dropped": dropped[:40], "jargon": jargon[:20], "bn_rejected": bn_rejected[:40],
                    "sections": {s: sum(c["section"] == s for c in calls) for s in decide.SECTION_ORDER},
                    "portfolio_basis": "equity holdings" if pv else "unknown: no holdings, so no sizes"})
    return {"status": "ok", **{k: v for k, v in r.notes.items()}}


def _held_summary(summary: str, note: dict | None) -> str:
    """A holding's call text with its plain risk line (thinly traded, or the exchange's ASM or GSM list) and, when the base rate rests
    on too little history or too few cases, "limited evidence". Code adds both after the model has answered; neither moves the chance."""
    if not note:
        return summary
    extra = [x for x in (note["risk_line"], note["limited_line"] if note["limited"] else None) if x]
    return " ".join([summary.strip(), *extra]) if extra else summary


def _store(db, run_id, day, calls, b, rules, runner_name, skeptic, unproven) -> None:
    """Replace the day's calls (delete, then insert) in one transaction."""
    db.execute("begin")
    try:
        db.execute("delete from calls where made_on = ?", [day])
        for c in calls:
            reasons = {k: c.get(k) for k in ("summary", "moved_by", "sized_by", "quantity", "tax_note", "tax_line", "since",
                                             "since_text", "why_code", "levels_why", "name", "industry", "upside_pct",
                                             "downside_pct", "blocked", "sell_kind", "broken_reason", "for", "against", "unknowns",
                                             "target_hit_rate", "target_hit_n")}
            db.execute("""insert into calls (run_id, made_on, symbol, kind, action, probability, base_rate, horizon_days, entry,
                          stop, target, size_inr, reasons, risks, news, runner, skeptic, unproven, section, expected_gain_inr,
                          hurdle, change_reason, summary_bn, would_buy_if, level_flag, warnings, acted_on, base_rate_n, raw_probability)
                          values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, null, ?, ?)""",
                       [run_id, day, c["symbol"], c["kind"], c["action"], c["probability"], c["base_rate"], b["horizon_days"],
                        c["entry"], c["stop"], c["target"], c["amount"], json.dumps(reasons, default=str),
                        json.dumps(c["risks"]), json.dumps(c["news_used"]), runner_name,
                        json.dumps(skeptic[c["symbol"]]) if c["symbol"] in skeptic else None, unproven, c["section"],
                        c["expected_gain_inr"], c["hurdle"], c["change_reason"], c["summary_bn"], c["would_buy_if"] or None,
                        c["level_flag"], json.dumps(c["warnings"]), c["base_rate_n"], c["raw_probability"]])
        db.execute("commit")
    except Exception:
        db.execute("rollback")
        raise


# ---- the dashboard's calls.json ----------------------------------------------------------------------------

def _pct(entry, level):
    return round(100 * (level - entry) / entry, 1) if entry and level else None


def _card(row: dict) -> dict:
    r = json.loads(row["reasons"]) if isinstance(row["reasons"], str) else (row["reasons"] or {})
    entry = row["entry"]
    return {"symbol": row["symbol"], "name": r.get("name") or row["symbol"], "section": row["section"],
            "probability": row["probability"], "base_rate": row["base_rate"], "base_rate_n": row["base_rate_n"],
            "expected_gain_inr": row["expected_gain_inr"], "hurdle_pct": round(100 * row["hurdle"], 2) if row["hurdle"] else None,
            "entry": entry, "stop": row["stop"], "target": row["target"], "stop_pct": _pct(entry, row["stop"]),
            "target_pct": _pct(entry, row["target"]), "quantity": r.get("quantity") or 0, "amount_inr": row["size_inr"],
            "sized_by": r.get("sized_by"), "reasons": r.get("moved_by") or [], "why": r.get("why_code"),
            "risks": json.loads(row["risks"]) if row["risks"] else [], "tax_line": r.get("tax_line"),
            "warnings": json.loads(row["warnings"]) if row["warnings"] else [], "summary": r.get("summary"),
            "summary_bn": row["summary_bn"], "since": r.get("since_text"), "would_buy_if": row["would_buy_if"], "sell_kind": r.get("sell_kind"),
            "level_flag": row["level_flag"], "change_reason": row["change_reason"], "acted_on": str(row["acted_on"]) if row["acted_on"] else None}


def site_payload(db, day: date) -> dict:
    """site/calls.json: {as_of, market_view, market_view_bn, gaps, buys, sells, follow, budget_line, sector_notes}."""
    made = db.execute("select max(made_on) from calls where made_on <= ? and section is not null", [day]).fetchone()[0]
    empty = {"as_of": str(made or day), "market_view": None, "market_view_bn": None, "gaps": [], "buys": [], "sells": [],
             "follow": [], "budget_line": None, "sector_notes": []}
    if not made:
        return empty
    cur = db.execute("select * from calls where made_on = ? and section is not null "
                     "qualify row_number() over (partition by symbol order by id desc) = 1", [made])
    cols = [c[0] for c in cur.description]
    rows = [dict(zip(cols, x)) for x in cur.fetchall()]
    cards = [_card(x) for x in rows]
    note = db.execute("select notes from runs where id = ?", [rows[0]["run_id"]]).fetchone() if rows else None
    notes = json.loads(note[0]) if note and note[0] else {}
    by_gain = lambda c: -(c["expected_gain_inr"] or 0)   # noqa: E731
    return {**empty, "market_view": notes.get("market_view"), "market_view_bn": notes.get("market_view_bn"),
            "gaps": notes.get("gaps", []), "budget_line": notes.get("budget_line"), "sector_notes": notes.get("sector_notes", []),
            "buys": sorted((c for c in cards if c["section"] == "buy"), key=by_gain),
            "sells": [c for c in cards if c["section"] in ("sell", "trim")],
            "follow": sorted((c for c in cards if c["section"] == "follow"), key=lambda c: -c["probability"])}
