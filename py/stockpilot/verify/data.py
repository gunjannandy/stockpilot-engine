"""Checks 1 to 6: the data on screen. Each takes a `Ctx` and returns a `Result`; none writes to the store."""
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from stockpilot.book import kinds, positions, units
from stockpilot.verify import FAIL, Gap, Result, flags, tolerance_ok, contract as contract_mod, reasoning_site


def _site_json(ctx, name):
    path = Path(ctx.site) / "data" / f"{name}.json"
    return json.loads(path.read_text()) if path.exists() else None


def _need_site(ctx, r: Result) -> bool:
    if not ctx.site or not (Path(ctx.site) / "data").is_dir():
        r.fail("there is no built site folder to check (build one with `sp build-site --out <folder>`, then pass `--site <folder>`)")
        return False
    return True


def _latest_close(db, symbol: str, day: date):
    row = db.execute("select close from prices where symbol = ? and date <= ? order by date desc, exchange = 'NSE' desc limit 1",
                     [symbol, day]).fetchone()
    return row[0] if row else None


# ---- 1: every number on screen equals the DB ---------------------------------------------------------------

def check_numbers(ctx) -> Result:
    r = Result(1, "Every number on screen equals the DB")
    if not _need_site(ctx, r):
        return r
    db, day = ctx.db, ctx.day
    portfolio, calls_json, today = _site_json(ctx, "portfolio"), _site_json(ctx, "calls"), _site_json(ctx, "today")
    if portfolio is None:
        return r.fail("portfolio.json is missing from the site")
    unreliable = flags.flagged_symbols(db)
    book, shown, compared = positions.held(db, day), {}, 0
    for h in portfolio.get("holdings", []):
        shown.setdefault(h["symbol"], h)
    derived, total = {}, 0.0
    for p in book:
        price = p.price or _latest_close(db, p.symbol, day) or p.avg_cost
        value = p.quantity * (price or 0)
        derived[p.symbol] = (p, price, value)
        total += value
    for symbol, (p, price, value) in derived.items():
        h = shown.get(symbol)
        if h is None:
            r.fail(f"{symbol}: held ({p.quantity:g} units, about ₹{value:,.0f}) but missing from the Portfolio page")
            continue
        compared += 1
        if not tolerance_ok(h["quantity"], p.quantity, absolute=1e-6):
            r.fail(f"{symbol}: the page says {h['quantity']:g} units, the DB says {p.quantity:g}")
        if not tolerance_ok(h["value"], value, absolute=1):
            r.fail(f"{symbol}: the page says value ₹{h['value']:,.0f}, the DB gives ₹{value:,.0f}")
        want_gain = (price / p.avg_cost - 1) if p.avg_cost and price else None
        if symbol in unreliable:
            if h.get("gain_pct") is not None:
                r.fail(f"{symbol}: its price series is flagged unreliable but the page still shows a gain of {h['gain_pct']:.0%}")
        elif not tolerance_ok(h.get("gain_pct"), want_gain, absolute=0.005):
            r.fail(f"{symbol}: the page says gain {h.get('gain_pct')}, the DB gives {None if want_gain is None else round(want_gain, 4)}")
        if total and not tolerance_ok(h.get("share"), value / total, absolute=0.0006):
            r.fail(f"{symbol}: the page says share {h.get('share')}, the DB gives {value / total:.3f}")
    for symbol in sorted(set(shown) - set(derived)):
        r.fail(f"{symbol}: on the Portfolio page but not held in the DB")
    if not tolerance_ok(portfolio.get("total_value"), total, absolute=1):
        r.fail(f"portfolio total: the page says ₹{portfolio.get('total_value'):,.0f}, the DB gives ₹{total:,.0f}")
    r.numbers = {"holdings_compared": compared, "portfolio_total_inr": round(total)}
    _tax_room(ctx, r, portfolio)
    n_calls = _call_numbers(ctx, r, calls_json, today)
    r.numbers["call_cards_compared"] = n_calls
    r.summary = (f"{compared} holdings, tax room and {n_calls} call cards re-derived from the DB; "
                 + ("all within 0.5%." if r.status != FAIL else f"{len(r.problems)} differ."))
    return r


def _tax_room(ctx, r: Result, portfolio) -> None:
    tax = portfolio.get("tax")
    row = ctx.db.execute("select payload from weekly_reports where section = 'tax' order by week_of desc limit 1").fetchone()
    if not row or not tax:
        r.numbers["tax_room"] = "none stored"
        return
    from stockpilot.analysis import tax as tax_mod
    stored = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    want = {"harvest_room": round(stored["harvest"]["gain_room"]),
            "realised_gain": round(sum(stored[k] for k in (*tax_mod.SHORT_POOLS, *tax_mod.LONG_POOLS)))}
    for key, value in want.items():
        if not tolerance_ok(tax.get(key), value, absolute=1):
            r.fail(f"tax {key}: the page says {tax.get(key)}, the stored weekly tax report gives {value}")
    r.numbers["tax_room"] = {"harvest_room": tax.get("harvest_room")}


def _call_numbers(ctx, r: Result, calls_json, today) -> int:
    db = ctx.db
    made = db.execute("select max(made_on) from calls where made_on <= ?", [ctx.day]).fetchone()[0]
    if made is None:
        return 0
    cols = ["symbol", "probability", "size_inr", "entry", "stop", "target", "expected_gain_inr", "section"]
    rows = {c[0]: dict(zip(cols, c)) for c in db.execute(
        f"select {', '.join(cols)} from calls where made_on = ? qualify row_number() over (partition by symbol order by id desc) = 1",
        [made]).fetchall()}
    n = 0

    def same(symbol, where, key, got, want, absolute):
        if not tolerance_ok(got, want, absolute=absolute):
            r.fail(f"{symbol} ({where}): {key} is {got} on the page, {want} in the DB")

    for group in ("buys", "sells", "follow"):
        for c in (calls_json or {}).get(group, []):
            row = rows.get(c["symbol"])
            if row is None:
                r.fail(f"{c['symbol']} (calls.json {group}): no call in the DB for {made}")
                continue
            n += 1
            same(c["symbol"], "calls.json", "chance", c.get("probability"), row["probability"], 0.0005)
            same(c["symbol"], "calls.json", "money at stake (amount_inr)", c.get("amount_inr"), row["size_inr"], 1)
            same(c["symbol"], "calls.json", "expected gain", c.get("expected_gain_inr"), row["expected_gain_inr"], 1)
    for group in ("buy", "sell", "watch_triggers", "keep", "not_yet"):
        for c in (today or {}).get(group, []):
            row = rows.get(c["symbol"])
            if row is None:
                r.fail(f"{c['symbol']} (today.json {group}): no call in the DB for {made}")
                continue
            n += 1
            same(c["symbol"], "today.json", "chance", c.get("probability"), row["probability"], 0.0005)
            same(c["symbol"], "today.json", "size_inr", c.get("size_inr"), row["size_inr"], 1)
    return n


# ---- 2: holdings versus Kite -------------------------------------------------------------------------------

def check_units(ctx) -> Result:
    r = Result(2, "Units explained by lots equal Kite's units")
    if not positions.last_kite_sync(ctx.db):
        return r.fail("there is no Kite snapshot, so nothing can be checked against Kite")
    found = units.gaps(ctx.db)
    for g in found:
        r.fail(g.message)
        r.gaps.append(Gap("holdings", g.symbol, "parse_failed", g.message))
    n = len(positions._kite(ctx.db))
    r.numbers = {"kite_holdings": n, "mismatches": len(found)}
    r.summary = f"{n} Kite holdings checked; " + ("every unit is explained by the lots." if not found else f"{len(found)} differ: " + ", ".join(g.symbol for g in found[:8]) + ".")
    return r


# ---- 3: price sanity ---------------------------------------------------------------------------------------

def check_prices(ctx) -> Result:
    r = Result(3, "Price sanity: no unexplained move over 40%")
    db = ctx.db
    found = flags.scan(db, ctx.day)
    stored = flags.stored(db)
    with_reason = 0
    for f in found:
        if (f.symbol, f.jump_date) not in stored:
            r.fail(f"{f.symbol}: {f.move:+.0%} on {f.jump_date} ({f.close_before:g} to {f.close_after:g}, {f.kind.replace('_', ' ')}) "
                   "with no corporate action, and the series is not flagged yet (run `sp verify` with write access)")
        why = flags.recorded_reason(f.symbol, f.jump_date)
        with_reason += bool(why)
        r.gaps.append(Gap("price_history", f.symbol, "parse_failed",
                          f"{f.move:+.0%} on {f.jump_date}, {f.kind.replace('_', ' ')}: hidden and left out of screens and calls"
                          + (f". Reason: {why}" if why else ". Reason not looked up yet.")))
    bad = {s for s, _ in {(f.symbol, f.jump_date) for f in found}}
    if bad and ctx.site and (Path(ctx.site) / "data").is_dir():
        _flagged_hidden(ctx, r, bad)
    kinds_count: dict[str, int] = {}
    for f in found:
        kinds_count[f.kind] = kinds_count.get(f.kind, 0) + 1
    r.numbers = {"flagged_series": len(bad), "jumps": len(found), "by_kind": kinds_count, "with_reason": with_reason,
                 "window_days": flags.WINDOW_DAYS, "threshold": flags.THRESHOLD}
    r.summary = (f"{len(found)} unexplained jumps in the last {flags.WINDOW_DAYS} days on {len(bad)} series, all excluded and hidden."
                 if found and r.status != FAIL else (f"{len(found)} unexplained jumps, not all handled." if found else "No unexplained move over 40%."))
    return r


def _flagged_hidden(ctx, r: Result, bad: set[str]) -> None:
    """A flagged series must not appear in the search, the ideas, the calls, a chart, or as a gain."""
    site = Path(ctx.site)
    search = {s["symbol"] for s in (_site_json(ctx, "search") or [])}
    ideas = {x["symbol"] for x in (_site_json(ctx, "ideas") or {}).get("ranking", [])}
    calls = _site_json(ctx, "calls") or {}
    called = {c["symbol"] for k in ("buys", "sells", "follow") for c in calls.get(k, [])}
    for symbol in sorted(bad):
        where = [n for n, s in (("search", search), ("ideas", ideas), ("calls", called)) if symbol in s]
        if (site / "data" / "history" / f"{symbol}.json").exists():
            where.append("a price chart")
        if where:
            r.fail(f"{symbol}: its price series is unreliable but it still shows up in {', '.join(where)}")
    for h in (_site_json(ctx, "portfolio") or {}).get("holdings", []):
        if h["symbol"] in bad and h.get("gain_pct") is not None:
            r.fail(f"{h['symbol']}: unreliable price series but the Portfolio page shows a gain")


# ---- 4: freshness ------------------------------------------------------------------------------------------

# (name, sql giving the newest date, trading days allowed behind `day`, or calendar days when `calendar`)
SOURCES = [
    ("Prices", "select max(date) from prices", 1, False),
    ("Index levels", "select max(date) from index_levels where name = 'Nifty 50'", 1, False),
    ("Fund NAVs", "select max(date) from navs", 3, False),
    ("USD to INR rate", "select max(date) from fx where pair = 'USDINR'", 4, False),
    ("Delivery percentages", "select max(date) from delivery", 3, False),
    ("Fund flows (FII, DII)", "select max(date) from flows", 4, False),
    ("Company announcements", "select max(announced_at) from announcements", 5, True),
    ("News headlines", "select max(published_at) from headlines", 5, True),
    ("Kite holdings", "select max(snapshot_at) from holdings", 3, True),
    ("Exchange watch list (ASM/GSM)", "select max(as_of) from surveillance", 7, True),
    ("Fundamentals", "select max(as_of) from fundamentals", 10, True),
    ("Quarterly results", "select max(filed_at) from quarterly", 120, True),
    ("Daily calls", "select max(made_on) from calls", 3, False),
]


def _trading_days_behind(db, last: date, day: date) -> int:
    if last >= day:
        return 0
    holidays = {d for (d,) in db.execute("select date from holidays").fetchall()}
    n, d = 0, last + timedelta(days=1)
    while d <= day:
        if d.weekday() < 5 and d not in holidays:
            n += 1
        d += timedelta(days=1)
    return n


def check_freshness(ctx) -> Result:
    r = Result(4, "Freshness: each source's newest row is within its allowed age")
    db, stale = ctx.db, []
    ages = {}
    for name, sql, allowed, calendar in SOURCES:
        try:
            newest = db.execute(sql).fetchone()[0]
        except Exception as err:    # noqa: BLE001
            r.fail(f"{name}: cannot be read ({str(err)[:100]})")
            continue
        if newest is None:
            stale.append(name)
            r.fail(f"{name}: no rows at all")
            r.gaps.append(Gap("freshness", name, "not_collected", "no rows"))
            continue
        newest_day = newest.date() if isinstance(newest, datetime) else newest
        behind = (ctx.day - newest_day).days if calendar else _trading_days_behind(db, newest_day, ctx.day)
        unit = "days" if calendar else "trading days"
        ages[name] = behind
        if behind > allowed:
            stale.append(name)
            r.fail(f"{name}: newest row is {newest_day}, {behind} {unit} behind (allowed {allowed})")
            r.gaps.append(Gap("freshness", name, "source_down", f"newest row {newest_day}, {behind} {unit} behind"))
    if stale and ctx.site and (Path(ctx.site) / "data").is_dir():
        meta = _site_json(ctx, "meta") or {}
        if (meta.get("status") or {}).get("ok") is True and set(stale) & {"Prices", "Kite holdings", "Daily calls", "Index levels"}:
            r.fail("the site says \"Everything is up to date\" while " + ", ".join(sorted(set(stale) & {'Prices', 'Kite holdings', 'Daily calls', 'Index levels'})) + " is stale")
    if ctx.site and (Path(ctx.site) / "data").is_dir():
        meta = _site_json(ctx, "meta") or {}
        newest = db.execute("select max(date) from prices where date <= ?", [ctx.day]).fetchone()[0]
        if meta.get("as_of") and newest and meta["as_of"] != str(newest):
            r.fail(f"the site is built on prices of {meta['as_of']} but the DB has {newest}")
    r.numbers = {"sources": len(SOURCES), "stale": stale, "age_by_source": ages}
    r.summary = f"{len(SOURCES)} sources checked; " + ("all within their allowed age." if not stale else f"stale: {', '.join(stale)}.")
    return r


# ---- 5: cross-source ---------------------------------------------------------------------------------------

NSE_BSE_TOLERANCE = 0.01     # the lane's rule: the two closes agree within 1%
NSE_BSE_HARD = 0.03          # ... and above 3% they fail the check; 1% to 3% on a liquid stock is two exchanges' closing auctions, listed as a note
NSE_BSE_FLOOR = 1e7          # both exchanges must have traded at least ₹1 crore: a close on a thin day is not a price
SECTOR_TOLERANCE = 0.03      # percentage points a sector index may differ from its stocks' median day move
NAV_TOLERANCE = 0.01


def check_cross_source(ctx) -> Result:
    r = Result(5, "Cross-source: NSE vs BSE, index vs sectors, fund NAV vs holdings")
    db = ctx.db
    day = db.execute("select max(date) from prices where date <= ?", [ctx.day]).fetchone()[0]
    both = db.execute("""select n.symbol, n.close, b.close, n.value from prices n join prices b
                         on b.symbol = n.symbol and b.date = n.date and b.exchange = 'BSE'
                         where n.exchange = 'NSE' and n.date = ? and n.close > 0 and b.close > 0
                         and n.value >= ? and b.value >= ?""", [day, NSE_BSE_FLOOR, NSE_BSE_FLOOR]).fetchall()
    off = sorted(((s, nc, bc) for s, nc, bc, _ in both if abs(nc / bc - 1) > NSE_BSE_TOLERANCE), key=lambda x: -abs(x[1] / x[2] - 1))
    for s, nc, bc in off:
        line = f"{s}: NSE closed at {nc:g} and BSE at {bc:g} on {day} ({nc / bc - 1:+.1%})"
        if abs(nc / bc - 1) > NSE_BSE_HARD:
            r.fail(line)
            r.gaps.append(Gap("price_check", s, "source_down", f"NSE {nc:g} vs BSE {bc:g} on {day}"))
        else:
            r.notes.append(line)
    r.numbers = {"nse_bse_pairs": len(both), "nse_bse_over_1pct": len(off), "nse_bse_over_3pct": sum(abs(nc / bc - 1) > NSE_BSE_HARD for _, nc, bc in off)}
    r.numbers["sectors"] = _sectors(ctx, r, day)
    r.numbers["fund_navs"] = _fund_navs(ctx, r)
    r.summary = (f"{len(both)} NSE/BSE pairs, {r.numbers['sectors']} sector indices and {r.numbers['fund_navs']} funds compared; "
                 + ("all agree." if r.status != FAIL else f"{len(r.problems)} disagree."))
    return r


def _sectors(ctx, r: Result, day) -> int:
    """A sector index's day move against the median day move of the stocks in that industry (NSE closes)."""
    db, n = ctx.db, 0
    if not ctx.sector_index or day is None:
        return 0
    prev = db.execute("select max(date) from prices where date < ?", [day]).fetchone()[0]
    for industry, index in ctx.sector_index.items():
        lv = db.execute("select date, close from index_levels where name = ? and date <= ? order by date desc limit 2", [index, day]).fetchall()
        if len(lv) < 2 or lv[0][0] != day:
            continue
        move = db.execute("""select median(t.close / y.close - 1), count(*) from prices t join prices y
                             on y.symbol = t.symbol and y.exchange = t.exchange and y.date = ?
                             join stocks s on s.symbol = t.symbol where t.date = ? and t.exchange = 'NSE' and s.industry = ?
                             and t.value > 1e7""", [prev, day, industry]).fetchone()
        if not move[0] or move[1] < 5:
            continue
        n += 1
        idx = lv[0][1] / lv[1][1] - 1
        if abs(idx - move[0]) > SECTOR_TOLERANCE:
            r.fail(f"{index}: moved {idx:+.1%} on {day} but the median of its {move[1]} stocks moved {move[0]:+.1%}")
    return n


def _fund_navs(ctx, r: Result) -> int:
    """Each fund on the Portfolio page: units times the newest NAV in the DB equals the page's value."""
    if not ctx.site or not (Path(ctx.site) / "data").is_dir():
        return 0
    portfolio = _site_json(ctx, "portfolio") or {}
    db, n = ctx.db, 0
    funds = {isin: code for code, isin in db.execute("select scheme_code, isin_growth from funds where isin_growth is not null").fetchall()}
    for h in portfolio.get("holdings", []):
        if kinds.canon(h.get("kind")) != "mf":
            continue
        code = funds.get(h["symbol"])
        if code is None:
            continue
        nav = db.execute("select nav from navs where scheme_code = ? and date <= ? order by date desc limit 1", [code, ctx.day]).fetchone()
        if not nav:
            r.fail(f"{h['symbol']}: a fund he holds has no NAV in the DB")
            continue
        n += 1
        want = h["quantity"] * nav[0]
        if not tolerance_ok(h.get("value"), want, rel=NAV_TOLERANCE, absolute=1):
            r.fail(f"{h['symbol']}: the page values the fund at ₹{h.get('value'):,.0f}; units times the newest NAV gives ₹{want:,.0f}")
    return n


# ---- 6: schema ---------------------------------------------------------------------------------------------

def check_schema(ctx) -> Result:
    r = Result(6, "Schema: every contract field is present, typed and non-null")
    if not _need_site(ctx, r):
        return r
    contract = Path(ctx.root) / "schemas" / "site-contract.md"
    problems, stats = contract_mod.check_site(ctx.site, contract)
    shape, objects = reasoning_site.contract_problems(ctx.site)         # every reasoning object, wherever the site carries one
    problems += shape
    r.fail(*problems[:60])
    if len(problems) > 60:
        r.problems.append(f"... and {len(problems) - 60} more")
    search = _site_json(ctx, "search") or []
    missing = [s["symbol"] for s in search if not (Path(ctx.site) / "data" / "history" / f"{s['symbol']}.json").exists()
               or not (Path(ctx.site) / "data" / "stock" / f"{s['symbol']}.json").exists()]
    if missing:
        r.fail(f"{len(missing)} stocks in search.json have no history or stock file, for example {', '.join(missing[:5])}")
    for (symbol,) in ctx.db.execute("select symbol from quarterly group by symbol having count(net_profit) = 0 order by symbol").fetchall():
        r.gaps.append(Gap("quarterly_results", symbol, "parse_failed", "net profit was not read from its filings: no quarters shown"))
    if ctx.previous_site and (Path(ctx.previous_site) / "data").is_dir():
        old, _ = contract_mod.check_site(ctx.previous_site, contract)
        r.fail(*[f"previous day: {p}" for p in old[:20]])
    r.numbers = {**stats, "problems": len(problems), "search_stocks": len(search), "reasoning_objects": objects}
    r.summary = f"{stats['files']} JSON files checked against {stats['contract_files']} contract sections; " + ("no problems." if r.status != FAIL else f"{len(r.problems)} problems.")
    return r
