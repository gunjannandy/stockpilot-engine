"""The consumer of `analyst_asks` (lane W queues them; lane E answers them). An owner presses "Ask the analyst" on a stock; this
sends that one stock, with its three blocks, to the analyst in its own runner call and keeps the answer on the ask
(`answer` json, `status` done). The answer is a second look, not a call: it is not stored in `calls`, never sized or scored,
and the stock's page shows it as the analyst's note until the next nightly run writes a newer one.
Capped at five stocks a run (the Worker's own daily cap). A failed call leaves the ask pending for the next run; one older
than three days is expired."""
import json
from datetime import date

from stockpilot import costs, dossier, journal, levels, reasoning
from stockpilot.analysis import screen
from stockpilot.calls import bn, brief as brief_mod, runner
from stockpilot.calls.decide import Rules

PER_RUN = 5
EXPIRES_AFTER_DAYS = 3
ANSWER_KEYS = ("probability", "summary", "summary_bn", "risks", "moved_by", "would_buy_if", "broken_reason")


def _pending(db) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {}
    for ask_id, symbol in db.execute("select id, symbol from analyst_asks where status = 'pending' order by id").fetchall():
        out.setdefault(symbol, []).append(ask_id)
    return out


def _brief(db, symbol: str, day: date, ctx, rules: Rules, pv: float, gaps: list[str], market: dict, regime: str, held: dict) -> dict:
    d = dossier.build(db, symbol, day, ctx=ctx)
    lv = levels.for_stock(d)
    adv = (d.get("price") or {}).get("liquidity_cr")
    hurdle = costs.hurdle_for(rules.max_single * pv if pv > 0 else 100_000, adv, rules.nifty_3m) if lv else None
    why = ["the owners asked the analyst to look at this stock" + (" (they hold it)" if symbol in held else "")]
    return brief_mod.build(day, regime, market, gaps, [brief_mod.entry(d, why, lv, hurdle)])


def run_pending(db, day: date, analyse, runners: list[str], rules: Rules = Rules(), liquidity_floor_cr: float = 1.0) -> dict:
    """Answer the pending asks, one runner call per stock. Returns {"answered": n, "failed": [symbols], "left": n}."""
    todo = _pending(db)
    out = {"answered": 0, "failed": [], "left": 0}
    if not todo:
        return out
    from stockpilot import readiness
    from stockpilot.book import positions
    result = screen.run(db, day, liquidity_floor_cr)
    held = {p.symbol: p for p in positions.held(db, day) if p.kind == "equity" and p.quantity > 0}
    ctx = dossier.context(db, day, result, list(held.values()), rules.sector_index)
    pv = sum(p.value for p in held.values())
    gaps = readiness.check(db, day)["gaps"]
    market = dossier.market(db, day, ctx, [], list(held))
    for symbol, ids in list(todo.items())[:PER_RUN]:
        try:
            b = _brief(db, symbol, day, ctx, rules, pv, gaps, market, ctx.regime, held)
            got = analyse(b, "analyst", runners)
            item = next((i for i in got["decisions"]["items"] if i["symbol"] == symbol), None)
            if item is None:
                raise runner.RunnerError(f"the analyst did not answer for {symbol}")
        except Exception as err:  # noqa: BLE001 - the ask stays pending; the other stocks still run
            journal.problem(db, "asks", f"Could not answer the ask for {symbol}: {err}", key=f"asks:{symbol}")
            out["failed"].append(symbol)
            continue
        item["summary_bn"], _ = bn.clean(item["summary"], item.get("summary_bn"))
        body = {k: item.get(k) for k in ANSWER_KEYS}
        us = symbol not in held and bool(db.execute("select 1 from prices where symbol = ? and exchange = 'NYSE' limit 1", [symbol]).fetchone())
        call = {"summary": item.get("summary"), "moved_by": item.get("moved_by"), "would_buy_if": item.get("would_buy_if"),
                "reasons": {"for": item.get("for"), "against": item.get("against")}, "action": "hold" if symbol in held else None}
        if not us and item.get("probability") is not None:         # the chance is "beat the Nifty": it means nothing for a US share
            call["probability"] = item["probability"]
        body["reasoning"] = reasoning.build(symbol, call=call, as_of=str(day))
        db.execute("update analyst_asks set status = 'done', done_at = current_timestamp, answer = ? where id in (select unnest(?))",
                   [json.dumps(body, default=str), ids])
        out["answered"] += 1
    db.execute("update analyst_asks set status = 'expired', done_at = current_timestamp "
               "where status = 'pending' and asked_on < ?", [date.fromordinal(day.toordinal() - EXPIRES_AFTER_DAYS)])
    out["left"] = db.execute("select count(*) from analyst_asks where status = 'pending'").fetchone()[0]
    return out
