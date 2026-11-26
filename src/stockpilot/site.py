"""sp build-site: read DuckDB, write the static dashboard to `site/`. HTML, CSS and JS come from `web/public/`;
every tab gets one JSON file under `site/data/`. Code writes every number and sentence; the model writes none."""
import json
import shutil
import statistics
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

from stockpilot.book import budget, kinds, not_now, positions
from stockpilot import feedback, forecast, fundcall, fundresearch, learn, reasoning, valuation
from stockpilot import gaps as gaps_mod
from stockpilot.analysis import allocation, analytics, screen, tax
from stockpilot.sources import fx
from stockpilot.calls import record
from stockpilot import site_export
from stockpilot.site_export import calls as export_calls, market as export_market, stock as export_stock
from stockpilot.site_export.io import write_json
from stockpilot.verify import flags as verify_flags

WEB = Path(__file__).resolve().parents[2] / "web" / "public"
IDEAS_TOP, NEAR_MISSES = 10, 10
WATCH_DAYS = 120
STALE_HOLDINGS_DAYS, STALE_DOCS_DAYS = 2, 8
BUY_ACTIONS, SELL_ACTIONS = ("buy", "add"), ("sell", "trim")


def _j(value):
    return json.loads(value) if isinstance(value, str) else value


_write = write_json


def _num(x, nd=4):
    return None if x is None else round(float(x), nd)


def _latest_report(db, section):
    """(week_of, payload) of the newest weekly report of this section, or None."""
    row = db.execute("select week_of, payload from weekly_reports where section = ? order by week_of desc limit 1",
                     [section]).fetchone()
    return (row[0], _j(row[1])) if row else None


def _money(x) -> str:
    return f"₹{abs(x):,.0f}"


def weekly_view(db, name, default=None):
    """One weekly section in the shape the Portfolio tab reads (it was weekly.to_site, stored in site_extras; see docs/status/b.md).
    `funds` prefers the weekly fund calls (R13) when they are as new as the plain review."""
    if name == "funds":
        calls, plain = _latest_report(db, "fund_calls"), _latest_report(db, "funds")
        if calls and (not plain or str(calls[0]) >= str(plain[0])):
            return calls[1]["calls"]
        return [{"name": f["name"], "verdict": f["verdict"], "why": f["why"]} for f in plain[1]["funds"]] if plain else default
    report = _latest_report(db, name)
    if not report:
        return default
    as_of, payload = report
    if name == "opportunities":
        names = dict(db.execute("select symbol, name from stocks").fetchall())
        return [{"name": names.get(p["symbol"], p["symbol"]), "why": p["why"]} for p in payload["picks"]]
    if name == "allocation":
        row = db.execute("select allocation from target_allocations order by id desc limit 1").fetchone()
        approved = json.loads(row[0]) if row else None
        approved = approved.get("target", approved) if approved else None
        wanted = {r["class"]: r["target"] for r in payload["rows"] if r["target"] is not None}
        proposed = wanted if wanted and wanted != approved else None
        return {"target": approved, "proposed": proposed, "approved": bool(approved) and proposed is None}
    h = payload["harvest"]
    notes = [w for w in payload["warnings"]]
    for v in payload.get("expected_vests", [])[:2]:
        when = "was due" if str(v["on"]) <= str(payload["as_of"]) else "should vest"
        notes.append(f"Expected: about {v['quantity']:g} {v['symbol']} shares {when} around {v['on']}. "
                     "Not counted until a Fidelity email or payslip confirms it.")
    for c in h["gain_candidates"][:3]:
        notes.append(f"Selling {c['quantity']:g} {c['symbol']} would book {_money(c['gain'])} of gain with no tax, "
                     f"and save about {_money(c['future_tax_saved'])} later.")
    for c in h["loss_candidates"][:3]:
        notes.append(f"{c['symbol']} is {_money(c['loss'])} down. Selling it books a loss that cuts tax on other gains.")
    gains = sum(payload[k] for k in (*tax.SHORT_POOLS, *tax.LONG_POOLS))
    fa = payload["schedule_fa"]
    return {"fy": payload["fy"], "realised_gain": round(gains), "harvest_room": round(h["gain_room"]), "notes": notes,
            "schedule_fa": f"Needed this year: you hold foreign shares ({len(fa)} lines in the tax pack)." if fa else None,
            "itr_pack": None}


def _latest_calls(db, day):
    made = db.execute("select max(made_on) from calls where made_on <= ?", [day]).fetchone()[0]
    cols = ["id", "made_on", "symbol", "kind", "action", "probability", "base_rate", "entry", "stop", "target",
            "size_inr", "reasons", "risks", "news", "runner", "skeptic", "unproven"]
    rows = db.execute(f"select {', '.join(cols)} from calls where made_on = ? "
                      "qualify row_number() over (partition by symbol order by id desc) = 1 order by probability desc",
                      [made]).fetchall() if made else []
    return made, [dict(zip(cols, r)) for r in rows]


def _mood(health, run_view):
    if run_view:
        return run_view
    b, up = health.get("breadth_above_200dma"), health.get("nifty_above_200dma")
    if b is None:
        return "Not enough data to judge the market today."
    trend = "The Nifty is above its 200-day average" if up else "The Nifty is below its 200-day average"
    tone = "steady" if 0.4 <= b <= 0.6 else ("strong" if b > 0.6 else "weak")
    return f"The market looks {tone}. {trend}, and {b:.0%} of stocks are above theirs."


def _call_card(c, names):
    r = _j(c["reasons"]) or {}
    return {"symbol": c["symbol"], "name": names.get(c["symbol"], c["symbol"]), "kind": c["kind"], "action": c["action"],
            "probability": _num(c["probability"]), "base_rate": _num(c["base_rate"]), "entry": _num(c["entry"], 2),
            "stop": _num(c["stop"], 2), "target": _num(c["target"], 2), "size_inr": _num(c["size_inr"], 0),
            "quantity": r.get("quantity") or 0, "tax_note": r.get("tax_note"), "summary": r.get("summary"), "why": r.get("why_code"),
            "moved_by": r.get("moved_by") or [], "risks": _j(c["risks"]) or [], "news": _j(c["news"]) or [],
            "skeptic": _j(c["skeptic"]), "unproven": bool(c["unproven"]), "sized_by": r.get("sized_by"), "sell_kind": r.get("sell_kind")}


def _budget(db, today, default_total, planned):
    month = today.strftime("%Y-%m")
    total = budget.for_month(db, today, default_total)
    return {"month": month, "total": total, "planned": planned, "left": total - planned}


def _headline(buys, sells):
    """The one sentence the page opens with: what to do today, or that there is nothing to do."""
    stock = lambda n: f"{n} stock{'' if n == 1 else 's'}"   # noqa: E731
    if buys and sells:
        return f"Buy {stock(buys)} and sell {sells} today."
    if buys:
        return f"Buy {stock(buys)} today."
    if sells:
        return f"Sell {stock(sells)} today."
    return "Nothing to do today."


def _today(db, day, budget_inr, names, watch, health, moved, prices=None):
    """`moved` maps a watchlist symbol to its reasons today; only those stocks are worth the father's time."""
    made, calls = _latest_calls(db, day)
    cards = [_call_card(c, names) for c in calls]
    site_export.annotate(cards, "action")
    for c in cards:
        c["watchlist"] = c["symbol"] in watch
    buy = [c for c in cards if c["action"] in BUY_ACTIONS]
    sell = [c for c in cards if c["action"] in SELL_ACTIONS]
    trig = [c for c in cards if c["symbol"] in moved and c not in buy + sell and c["kind"] != "holding"]
    for c in trig:
        c["why_today"] = "; ".join(moved[c["symbol"]][:2])
    keep = [c for c in cards if c["kind"] == "holding" and c not in buy + sell]
    rest = [c for c in cards if c not in buy + sell + trig + keep]
    note = db.execute("select notes from runs where job = 'daily_decide' and status = 'ok' "
                      "order by started_at desc limit 1").fetchone()
    view = (_j(note[0]) or {}).get("market_view") if note and note[0] else None
    planned = round(sum(c["size_inr"] or 0 for c in buy))
    return {"as_of": str(made or day), "headline": _headline(len(buy), len(sell)), "market_mood": _mood(health, view), "buy": buy, "sell": sell,
            "watch_triggers": trig, "keep": keep, "not_yet": rest, "nothing_to_do": not (buy or sell),
            "budget": _budget(db, day, budget_inr, planned)}


def _screen_views(result, names, watch, held, calls_by):
    ranked = [c for c in result["candidates"] if not c["flags"] and c["symbol"] not in held]   # ideas are for what is not owned
    metric = lambda c, k: _num(c["metrics"].get(k))   # noqa: E731
    row = lambda i, c: {"rank": i, "symbol": c["symbol"], "name": names.get(c["symbol"], c["symbol"]),   # noqa: E731
                        "industry": c["industry"], "composite": _num(c["composite"], 3),
                        "scores": {k: _num(v, 2) for k, v in c["scores"].items()}, "close": metric(c, "close"),
                        "pe": metric(c, "pe"), "roe": metric(c, "roe"), "ret_6m": metric(c, "ret_6m"),
                        "watchlist": c["symbol"] in watch, "held": c["symbol"] in held,
                        "verdict": (calls_by.get(c["symbol"]) or {}).get("action")}
    return ranked, row


def _attach(why, *lists):
    """`reasoning` on every row that has a stock behind it and something to say; a row with nothing keeps no key."""
    for rows in lists:
        for r in rows:
            if r.get("symbol") and (obj := why.object(r["symbol"])):
                r["reasoning"] = obj


def _trigger(c):
    """What would move a near miss into the buy list, in plain words."""
    weakest = min(c["scores"], key=c["scores"].get)
    m = c["metrics"]
    if weakest == "momentum" and m.get("dist_200dma") is not None and m["dist_200dma"] < 0 and m.get("close"):
        level = m["close"] / (1 + m["dist_200dma"])
        return f"Closing above its 200-day average (about ₹{level:,.0f}) would lift its trend score."
    text = {"momentum": "A stronger 6- and 12-month price trend.", "quality": "Better returns on capital or less debt.",
            "value": "A cheaper price against earnings.", "risk": "Calmer price swings."}
    return text[weakest]


def _market(db, result, as_of, now_day):
    sectors: dict[str, list] = {}
    for c in result["candidates"]:
        if not c["flags"] and c["industry"]:
            sectors.setdefault(c["industry"], []).append(c["metrics"])
    sector_rows = []
    for name, ms in sectors.items():
        rets = [m["ret_6m"] for m in ms if m.get("ret_6m") is not None]
        above = [m["dist_200dma"] > 0 for m in ms if m.get("dist_200dma") is not None]
        if rets:
            sector_rows.append({"industry": name, "ret_6m": _num(statistics.median(rets)), "n": len(ms),
                                "above_200dma": _num(sum(above) / len(above), 2) if above else None})
    sector_rows.sort(key=lambda r: r["ret_6m"], reverse=True)
    pe = db.execute("select date, pe from index_levels where name = 'Nifty 50' and pe is not null and date <= ? "
                    "order by date", [as_of]).fetchall()
    val = {"pe_now": None, "percentile": None, "verdict": None}
    if pe:
        now = pe[-1][1]
        pctile = round(100 * sum(1 for _, p in pe if p <= now) / len(pe))
        val = {"pe_now": _num(now, 1), "percentile": pctile, "low": _num(min(p for _, p in pe), 1),
               "high": _num(max(p for _, p in pe), 1),
               "verdict": ("Expensive against its own history." if pctile >= 80 else
                           "Cheap against its own history." if pctile <= 30 else "About normal against its own history.")}
    events = [{"date": str(d), "text": desc} for d, desc in db.execute(
        "select date, description from holidays where date > ? and date <= ? order by date",
        [now_day, now_day + timedelta(days=45)]).fetchall()]
    h = result["health"]
    return {"as_of": str(as_of), "headline": _mood(h, None), "breadth": h["breadth_above_200dma"], "nifty_above_200dma": h["nifty_above_200dma"],
            "sectors": sector_rows, "valuation": val, "events": events,
            "flows": None}


def _watchlist(db, result, names, calls_by, as_of, closes):
    watch = [s for s, in db.execute("select distinct symbol from watchlist where removed_at is null and exchange <> 'AMFI' "
                                    "order by symbol").fetchall()]
    by = {c["symbol"]: c for c in result["candidates"]}
    ann: dict[str, list] = {}
    for sym, at, subject in db.execute("select symbol, announced_at, subject from announcements where "
                                       "announced_at >= ? order by announced_at desc",
                                       [as_of - timedelta(days=14)]).fetchall():
        ann.setdefault(sym, []).append((at, subject))
    vol = {s: (v, a) for s, v, a in db.execute(
        """select symbol, arg_max(volume, date), avg(volume) from (select * from prices where exchange = 'NSE'
           and date <= ? and date > ? ) group by symbol""", [as_of, as_of - timedelta(days=30)]).fetchall()}
    rows = []
    for s in watch:
        c = by.get(s)
        m = c["metrics"] if c else {}
        close = m.get("close")
        d200 = m.get("dist_200dma")
        d50 = None
        if close:
            tail = [x for d, x in closes.get(s, []) if d <= as_of][-50:]
            d50 = _num(close / (sum(tail) / len(tail)) - 1) if len(tail) >= 50 else None
        v, a = vol.get(s, (None, None))
        spike = _num(v / a, 1) if v and a else None
        notes = ann.get(s, [])
        actions = [t for _, t in notes if any(k in t.lower() for k in ("dividend", "split", "bonus", "rights", "buyback"))]
        results = next((t for _, t in notes if "result" in t.lower()), None)
        call = calls_by.get(s)
        score, why = 0, []
        if spike and spike >= 2:
            score += 3
            why.append(f"Trading {spike:g}x its usual volume")
        if d200 is not None and abs(d200) < 0.01:
            score += 2
            why.append("At its 200-day average")
        if actions:
            score += 2
            why.append("Corporate action announced")
        if results:
            score += 1
            why.append("Results coming")
        if c and c["flags"]:
            score += 2
            why.append("; ".join(c["flags"]))
        if call and call["action"] in BUY_ACTIONS + SELL_ACTIONS:
            score += 4
            why.append(f"Today's call: {call['action']}")
        rows.append({"symbol": s, "name": names.get(s, s), "close": _num(close, 2), "dist_50dma": d50,
                     "dist_200dma": _num(d200), "volume_spike": spike, "actions": actions,
                     "results_date_note": results, "attention": score, "why": why,
                     "verdict": call["action"] if call else None, "illiquid": bool(c and c["flags"])})
    rows.sort(key=lambda r: (-r["attention"], r["symbol"]))
    return {"rows": rows}


def _long_term_note(lots):
    """One line per holding: all long-term, or how many shares turn long-term next, and when."""
    if not lots:
        return None
    waiting = sorted((l for l in lots if not l["long_term"] and l["turns_long_term_on"]), key=lambda l: l["turns_long_term_on"])
    if not waiting:
        return "All long-term" if all(l["long_term"] for l in lots) else None
    when = waiting[0]["turns_long_term_on"]
    qty = sum(l["quantity"] for l in waiting if l["turns_long_term_on"] == when)
    d = date.fromisoformat(when)
    return f"{qty:g} turn long-term on {d.day} {d:%b %Y}"


def _lakh(n):
    return f"₹{n / 1e7:.1f} crore" if n >= 1e7 else f"₹{n / 1e5:.1f} lakh"


def _holdings(db, names, calls_by, last_prices, today, held=None):
    snap = positions.last_kite_sync(db)
    marked = {r[0] for r in db.execute("select symbol from long_term_marks").fetchall()}
    unreliable = verify_flags.flagged_symbols(db)     # lane V: a series with an unexplained jump shows no gain (the cost may be on the other side of a split)
    out = []
    for p in (positions.held(db, today) if held is None else held):
        price = p.price or last_prices.get(p.symbol) or p.avg_cost
        lots = [{"acquired_on": str(l.acquired_on), "quantity": l.quantity, "cost": l.cost,
                 "days_held": (today - l.acquired_on).days, "long_term": l.long_term(today),
                 "turns_long_term_on": str(l.turns_long_term_on) if l.turns_long_term_on else None} for l in p.lots]
        cls = allocation.asset_class(db, {"kind": p.kind, "isin": p.isin})
        call = calls_by.get(p.symbol) or {}
        out.append({"kind": p.kind, "class": cls, "group": "RSUs" if cls == "foreign" else allocation.LABELS.get(cls, "Other"), "symbol": p.symbol,
                    "name": names.get(p.symbol, p.name), "quantity": p.quantity, "avg_cost": _num(p.avg_cost, 2),
                    "price": _num(price, 2), "value": _num(p.quantity * (price or 0), 0),
                    "gain_pct": _num(price / p.avg_cost - 1) if p.avg_cost and price and p.symbol not in unreliable else None,
                    "verdict": call.get("action"), "lots": lots, "tax_note": _long_term_note(lots),
                    "probability": _num(call.get("probability")), "source": p.source, "check": p.check,
                    "long_term": p.symbol in marked})
    out.sort(key=lambda h: -(h["value"] or 0))
    return snap, out


def _rsu(db, today, portfolio_value):
    """Lane R: the RSU pane's data (cost, profit, lots and where each came from, vests, tax if sold, the trim call)."""
    from stockpilot.book import rsu_view
    from stockpilot.calls.decide import Rules
    row = db.execute("select close from prices where symbol = ? and exchange = 'NYSE' and date <= ? order by date desc limit 1",
                     [rsu_view.SYMBOL, today]).fetchone() or db.execute(
        "select price_usd from fidelity_holdings where symbol = ? order by as_of desc limit 1", [rsu_view.SYMBOL]).fetchone()
    return rsu_view.build(db, today, price_usd=row[0] if row else None, portfolio_value=portfolio_value, max_single=Rules().max_single)


def _tax(db, pack):
    tax = weekly_view(db, "tax")
    if tax and pack:
        tax = {**tax, "itr_pack": pack.get(tax["fy"])}
    return tax


def _pack_zips(pack_dir, out: Path) -> dict:
    """Zip each built tax pack into site/downloads/ and return {fy label: url}. The site is behind the login."""
    found = {}
    for folder in sorted(Path(pack_dir).glob("*")) if pack_dir and Path(pack_dir).is_dir() else []:
        if (folder / "summary.json").exists():
            (out / "downloads").mkdir(exist_ok=True)
            shutil.make_archive(str(out / "downloads" / f"tax-pack-{folder.name}"), "zip", folder)
            found[folder.name] = f"downloads/tax-pack-{folder.name}.zip"
    return found


def _portfolio(db, names, calls_by, last_prices, today, budget, pack=None, held=None):
    snap, holdings = _holdings(db, names, calls_by, last_prices, today, held)
    total = sum(h["value"] or 0 for h in holdings) or 1
    cur: dict[str, float] = {}
    for h in holdings:
        cur[h["class"]] = cur.get(h["class"], 0) + (h["value"] or 0) / total
    alloc = weekly_view(db, "allocation", {}) or {}
    for h in holdings:
        h["share"] = _num((h["value"] or 0) / total, 3)
    headline = "No holdings yet. Press Sync now to bring them in." if not holdings else f"Worth about {_lakh(total)}."
    if cur:
        top = max(cur, key=cur.get)
        label = allocation.LABELS.get(top, top)
        tgt = (alloc.get("target") or {}).get(top)
        headline += f" {cur[top]:.0%} is in {label}" + (f"; your target is {tgt:.0%}." if tgt is not None else ".")
    return {"snapshot_at": str(snap) if snap else None, "headline": headline, "total_value": round(total), "holdings": holdings,
            "allocation": {"current": {k: round(v, 3) for k, v in cur.items()}, "labels": allocation.LABELS, "target": alloc.get("target"),
                           "proposed": alloc.get("proposed"), "approved": alloc.get("approved", False)},
            "budget": budget, "funds": weekly_view(db, "funds", []), "opportunities": weekly_view(db, "opportunities", []),
            "tax": _tax(db, pack), "rsu": _rsu(db, today, total if holdings else 0)}


def _record(db):
    """The Record tab: the summary and calibration come from `record` (the same numbers as status.json); the call list is here."""
    cols = ["id", "made_on", "symbol", "action", "probability", "base_rate", "size_inr", "score_1m", "score_3m", "score_6m"]
    rows = [dict(zip(cols, r)) for r in db.execute(
        f"select {', '.join(cols)} from calls "
        "qualify row_number() over (partition by made_on, symbol order by id desc) = 1 "
        "order by made_on desc, probability desc limit 1000").fetchall()]
    got = record.summary(db)
    summary, calibration = {}, {}
    for h in ("1m", "3m", "6m"):
        w = got[h]
        summary[h] = {"n": w["n"]}
        if w["n"]:
            summary[h].update(hit_rate=round(w["hit_rate"], 3), brier=round(w["brier"], 4))
            if w["base_n"]:
                summary[h].update(base_brier=round(w["base_brier"], 4))
        calibration[h] = record.calibration_table(db, h)
    scored3 = got["scored_3m"]
    if scored3:
        headline = (f"{'Early days. ' if scored3 < 30 else ''}Over 3 months we beat the Nifty after costs and tax "
                    f"{summary['3m']['hit_rate']:.0%} of the time, from {scored3} calls.")
        if got["model_added_value"] is not None:
            headline += (" The model does better than the base rate alone." if got["model_added_value"]
                         else " The model does not yet beat the base rate alone.")
    else:
        headline = "No call has a result yet. The first ones are scored a month after they are made."
    learned = record.learning(db)
    return {"headline": headline, "summary": summary, "calibration": calibration, "unproven": got["unproven"],
            "learning": {h: {k: (round(v, 3) if isinstance(v, float) else v) for k, v in learned[h].items()} for h in ("1m", "3m", "6m")},
            "learning_lines": learned["lines"],
            "scored_3m": scored3, "model_added_value": got["model_added_value"],
            "dates": sorted({str(r["made_on"]) for r in rows}, reverse=True),
            "calls": [{**r, "made_on": str(r["made_on"]), "probability": _num(r["probability"], 3),
                       "base_rate": _num(r["base_rate"], 3)} for r in rows]}


def _health(db, today, now, snap, token_specs=()):
    f = lambda sql: db.execute(sql).fetchone()[0]   # noqa: E731
    fresh = [("Prices", f("select max(date) from prices")), ("Company numbers", f("select max(as_of) from fundamentals")),
             ("Fund prices (NAV)", f("select max(date) from navs")), ("Announcements", f("select max(announced_at) from announcements")),
             ("Holdings", snap)]
    freshness = []
    for name, when in fresh:
        d = when.date() if isinstance(when, datetime) else when
        freshness.append({"name": name, "when": str(when) if when else None, "days_old": (today - d).days if d else None})
    runs = db.execute("select job, started_at, finished_at, status, notes from runs "
                      "where not (job = 'queue' and status = 'ok') order by started_at desc limit 30").fetchall()
    problems = db.execute("select id, coalesce(last_seen, seen_at), job, severity, message, resolution, issue_url, "
                          "coalesce(count, 1) from problems order by coalesce(last_seen, seen_at) desc limit 30").fetchall()
    queue = db.execute("select id, kind, payload, created_at, applied_at, status from requests "
                       "order by created_at desc limit 30").fetchall()
    tokens = []
    for t in token_specs or []:
        tokens.append({**t, "days_left": (date.fromisoformat(t["expires_on"]) - today).days})
    needs = [f"{t['name']} {'expires in ' + str(t['days_left']) + ' days' if t['days_left'] > 0 else 'has expired'}."
              for t in tokens if t["days_left"] <= 7]
    needs += [f"{f['name']} {'are' if f['name'] == 'Company numbers' else 'is'} {f['days_old']} days old." for f in freshness
              if f["days_old"] is not None and f["days_old"] > 3]
    from stockpilot.sources import navhistory
    needs += navhistory.gaps(db, today)
    open_problems = db.execute("select count(*) from problems where resolution is null").fetchone()[0]
    open_gaps = gaps_mod.open_gaps(db)
    total = len(needs) + open_problems + len({g["area"] for g in open_gaps})   # one thing per area; the Gaps card lists each
    headline = ("Everything is working." if not total else "One thing needs you." if total == 1 else f"{total} things need you.")
    if open_gaps:
        needs.append(gaps_mod.weekly_note(db))
    return {"headline": headline, "needs": needs, "open_problems": open_problems,
            "gaps": [{"area": g["area"], "subject": g["subject"], "reason": g["reason_text"], "detail": g["detail"],
                      "since": str(g["first_seen"])} for g in open_gaps], "runs": [{"job": j, "started_at": str(s), "finished_at": str(e) if e else None, "status": st,
                      "error": (_j(n) or {}).get("error") if n else None} for j, s, e, st, n in runs],
            "problems": [{"id": i, "seen_at": str(s), "job": j, "severity": sv, "message": m, "resolution": r, "url": u,
                          "count": n} for i, s, j, sv, m, r, u, n in problems],
            "queue": [{"id": i, "kind": k, "payload": _j(p), "at": str(c), "applied_at": str(a) if a else None,
                       "status": st or "pending"} for i, k, p, c, a, st in queue],
            "tokens": tokens, "freshness": freshness}


def _lookup(result, names, calls_by, watch, held):
    by_ind: dict[str, list] = {}
    for c in result["candidates"]:
        by_ind.setdefault(c["industry"], []).append(c)
    sheets = {}
    for c in result["candidates"]:
        peers = [p for p in by_ind[c["industry"]] if p["symbol"] != c["symbol"] and not p["flags"]]
        pes = sorted(p["metrics"]["pe"] for p in peers if (p["metrics"].get("pe") or 0) > 0)
        pe_range = {"peers": len(pes)}
        if pes:
            pe_range.update(low=_num(pes[0], 1), median=_num(statistics.median(pes), 1), high=_num(pes[-1], 1),
                            own=_num(c["metrics"].get("pe"), 1))
        keys = ["close", "ret_6m", "ret_12m", "dist_200dma", "pe", "pb", "roe", "roce", "debt_to_equity",
                "profit_cagr_3y", "vol_1y", "max_dd_1y", "adv_3m_cr"]
        call = calls_by.get(c["symbol"])
        sheets[c["symbol"]] = {
            "symbol": c["symbol"], "name": names.get(c["symbol"], c["symbol"]), "industry": c["industry"],
            "composite": _num(c["composite"], 3), "scores": {k: _num(v, 2) for k, v in c["scores"].items()},
            "watchlist": c["symbol"] in watch, "held": c["symbol"] in held,
            "metrics": {k: _num(c["metrics"].get(k)) for k in keys}, "flags": c["flags"], "pe_range": pe_range,
            "verdict": {k: (_num(call[k], 3) if k == "probability" else call[k])
                        for k in ("action", "probability", "summary", "made_on")} if call else None,
            "peers": [{"symbol": p["symbol"], "name": names.get(p["symbol"], p["symbol"]), "composite": _num(p["composite"], 3)}
                      for p in sorted(peers, key=lambda p: -p["composite"])[:5]]}
    return sheets


def _account_pages(db, out: Path, today: date) -> None:
    """New page files (R8): smallcase against his own trades, and his own record. A failure here is a problem on the
    Health tab, never a failed build: the other pages do not depend on these."""
    from stockpilot import journal
    from stockpilot.book import record, smallcase
    for name, write in (("smallcase", smallcase.write), ("own_record", record.write)):
        try:
            write(db, out, today)
        except Exception as err:  # noqa: BLE001
            journal.problem(db, "site", f"The {name} page could not be built: {err}", key=f"site:{name}")


def _stale_calls_note(db, today: date, now: datetime, made: date | None, as_of: date) -> str | None:
    """Plain words when the newest calls are older than the latest trading day whose crunch time has passed, else None."""
    from stockpilot.sources import exchange
    from stockpilot.jobs.due import CRUNCH_FROM_HOUR
    expected = today if now.hour >= CRUNCH_FROM_HOUR else today - timedelta(days=1)
    while not exchange.is_trading_day(db, expected):
        expected -= timedelta(days=1)
    if made is None or made >= expected:
        return None
    nse = db.execute("select max(date) from prices where exchange = 'NSE' and date <= ?", [today]).fetchone()[0]
    if nse is None or nse < expected:
        which = "today's" if expected == today else f"{expected:%a %d %b}'s"
        return f"Calls are from {made:%a %d %b}; {which} prices were not out."
    return f"Calls are from {made:%a %d %b}; the newer calls have not been made yet."


def build(db: duckdb.DuckDBPyConnection, out: Path | str, today: date | None = None, budget_inr: float = 100000,
          liquidity_floor_cr: float = 1.0, now: datetime | None = None, pack_dir=None, tokens=()) -> dict:
    """`tokens`: [{name, expires_on}] for the Health tab's countdowns (from config; see jobs.ship.token_list)."""
    out, today, now = Path(out), today or date.today(), now or datetime.now()
    out.mkdir(parents=True, exist_ok=True)
    for f in WEB.iterdir():
        if f.is_file():
            shutil.copy(f, out / f.name)
        elif f.is_dir():        # screens/ and vendor/: index.html loads them, so a site without them has no Holdings, Stock or Funds
            shutil.copytree(f, out / f.name, dirs_exist_ok=True)
    as_of = db.execute("select max(date) from prices where date <= ?", [today]).fetchone()[0] or today
    result = screen.run(db, as_of, liquidity_floor_cr)
    names = dict(db.execute("select symbol, name from stocks").fetchall())
    watch = {s for s, in db.execute("select symbol from watchlist where removed_at is null and exchange <> 'AMFI'").fetchall()}
    fund_watch = {s for s, in db.execute("select symbol from watchlist where removed_at is null and exchange = 'AMFI'").fetchall()}
    made, calls = _latest_calls(db, today)
    calls_by = {c["symbol"]: {**c, **{k: v for k, v in (_j(c["reasons"]) or {}).items() if k == "summary"}} for c in calls}
    prices = {c["symbol"]: c["metrics"].get("close") for c in result["candidates"]}
    book = positions.held(db, today)         # once: every tab below reads this list
    held = {p.symbol for p in book}
    ranked_now = [c for c in result["candidates"] if not c["flags"] and c["symbol"] not in held]   # same list as the Ideas tab
    triggers = {c["symbol"]: _trigger(c) for c in ranked_now[IDEAS_TOP:IDEAS_TOP + NEAR_MISSES]}
    why = reasoning.Book(db, today, result, triggers)           # lane F1: one `reasoning` object per stock, shared by every tab
    industries = {c["symbol"]: c["industry"] for c in result["candidates"]}
    exchanges = {s: "NSE" for s in held | watch | {c["symbol"] for c in calls}}
    exchanges.update({c["symbol"]: c["exchange"] for c in result["candidates"]})    # searchable stocks, owned, watched and called ones
    for symbol in verify_flags.flagged_symbols(db):      # lane V: no chart and no numbers for a series with an unexplained jump
        exchanges.pop(symbol, None)
    export_stock.write_all(db, out, exchanges, names, industries, as_of, today, why)     # first: the other tabs reuse its objects
    closes = analytics.adjusted_closes_many(db, watch, as_of - timedelta(days=WATCH_DAYS))   # the watchlist's distance from its 50-day average

    watchlist = _watchlist(db, result, names, calls_by, as_of, closes)
    moved = {r["symbol"]: r["why"] for r in watchlist["rows"] if r["attention"] >= 2 and r["why"] and r["symbol"] not in held}
    today_tab = _today(db, today, budget_inr, names, watch, result["health"], moved, prices)
    shown = [c for k in ("buy", "sell", "watch_triggers", "keep", "not_yet") for c in today_tab[k]]
    today_tab["since"] = export_calls.since(db, today, shown)
    today_tab["unusual"] = export_calls.unusual(
        db, as_of, held | watch | {c["symbol"] for c in shown}, names, held, watch, shown,
        {c["symbol"]: c["metrics"].get("dist_200dma") for c in result["candidates"]})
    ranked, row = _screen_views(result, names, watch, held, calls_by)
    ideas = {"as_of": str(as_of), "ranking": [row(i + 1, c) for i, c in enumerate(ranked[:IDEAS_TOP])],
             "near_misses": [{**row(IDEAS_TOP + i + 1, c), "trigger": _trigger(c)}
                             for i, c in enumerate(ranked[IDEAS_TOP:IDEAS_TOP + NEAR_MISSES])],
             "excluded": [{"symbol": s, "why": w} for s, w in sorted(result["excluded"].items())][:50]}
    _attach(why, watchlist["rows"], ideas["ranking"], ideas["near_misses"], shown)
    snap = positions.last_kite_sync(db)
    portfolio = _portfolio(db, names, calls_by, prices, today, today_tab["budget"], _pack_zips(pack_dir, out), book)
    _attach(why, portfolio["holdings"])
    health = _health(db, today, now, snap, tokens)
    holdings_days = (today - snap.date()).days if snap else None
    docs = db.execute("select max(finished_at) from runs where job = 'weekly' and status = 'ok'").fetchone()[0]
    docs_days = (today - docs.date()).days if docs else None
    late = []
    if holdings_days is None:
        late.append("Holdings have never been synced.")
    elif holdings_days > STALE_HOLDINGS_DAYS:
        late.append(f"Holdings are {holdings_days} days old.")
    if docs_days is None or docs_days > STALE_DOCS_DAYS:
        late.append("Documents have not been read for over a week." if docs_days else "Documents have not been read yet.")
    calls_note = _stale_calls_note(db, today, now, made, as_of)
    today_tab["calls_note"] = calls_note
    status = {"ok": not late and not calls_note,
              "text": " ".join(filter(None, [calls_note, *late])) + (" Press Sync now." if late else "")
              if (late or calls_note) else "Everything is up to date."}
    meta = {"built_at": now.isoformat(timespec="minutes"),
            "built_at_utc": now.astimezone(timezone.utc).isoformat(timespec="seconds"), "as_of": str(as_of), "calls_on": str(made) if made else None, "calls_note": calls_note, "status": status,
            "holdings": {"at": str(snap) if snap else None, "days_old": holdings_days,
                         "stale": holdings_days is None or holdings_days > STALE_HOLDINGS_DAYS},
            "documents": {"at": str(docs) if docs else None, "days_old": docs_days,
                          "stale": docs_days is None or docs_days > STALE_DOCS_DAYS}}
    market = _market(db, result, as_of, today)
    flows = export_market.flows(db, as_of)
    if flows:
        market["flows"] = {k: flows[k] for k in ("as_of", "days", "totals", "sentence")}
    tabs = {"meta": meta, "today": today_tab, "market": market, "ideas": ideas,
            "watchlist": watchlist, "portfolio": portfolio,
            "record": _record(db), "health": health, "lookup": _lookup(result, names, calls_by, watch, held),
            "search": [{"symbol": c["symbol"], "name": names.get(c["symbol"], c["symbol"]), "exchange": c["exchange"]}
                       for c in result["candidates"]]}
    for name, body in tabs.items():
        _write(out, name, body)
    payload = forecast.site_payload(db, today)                  # the forecaster's calls; the tabs above are untouched
    for k in ("buys", "sells", "follow"):
        site_export.annotate(payload[k], "section")
        _attach(why, payload[k])
    _write(out, "calls", payload)
    _write(out, "settings", not_now.settings_payload(db, today, budget_inr))
    _write(out, "feedback", feedback.site_payload(db))
    _write(out, "learned", learn.payload(db, today, result))
    held_funds = {p.isin for p in book if p.kind == "mf" and p.isin}
    fund_calls = fundcall.site_payload(db)                      # the weekly fund calls (R13); the Portfolio `funds` list gains keys too
    research = {**fundresearch.research(db, as_of, held_funds, fund_watch),
                "mine": [p.isin for p in book if p.kind == "mf" and p.isin]}
    fundresearch.attach_calls(research, fund_calls["calls"])    # a held fund carries its call and SIP (lane M)
    _write(out, "fund_research", research)                      # the Mutual funds tab
    _write(out, "funds", fund_calls)
    _account_pages(db, out, today)
    export_market.write_all(db, out, as_of)
    return meta
