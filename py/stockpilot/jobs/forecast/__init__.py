"""The forecast Job: turn the nightly mechanical forecast into calls, one new row per stock per day, append-only.

Public data only. Inputs: the mechanical results file (chance and price band per horizon, with the walk-forward report for
the base rate and its case count), past scored calls for the confidence line, and the backtest note for "limited evidence".
A call that breaks a rule is held back and reported; the run fails only when too many do. Rows go to the Worker's own
append-only door `/api/calls/publish`, because the shared publish door replaces a dataset each run."""
import json
import re
from datetime import date
from pathlib import Path

from .templates import render
from .verdict import BUY_AT, SELL_AT, similar, verdict

KIND = "forecast"
MODEL_VERSION = "mech-v1"
HORIZONS = {63: "3m"}      # the call card shows the three-month chance; the six-month one stays in the file
CHANCE_MIN, CHANCE_MAX, BASE_CASES_MIN, MOVE_POINTS = 0.05, 0.95, 30, 8
HELD_LIMIT = 0.10


def backtest_note(path: Path | None) -> dict[int, float]:
    """{horizon days: base rate} from docs/backtest.md lines like `63 days: 53%`; empty when there is no note."""
    if path is None or not path.exists():
        return {}
    return {int(m[1]): float(m[2]) / 100 for m in re.finditer(r"(\d+)\s+days:\s*([\d.]+)%", path.read_text())}


def limited(cases: int, rate: float | None, note: float | None) -> bool:
    if cases < BASE_CASES_MIN:
        return True
    return rate is not None and note is not None and abs(rate - note) * 100 > MOVE_POINTS


def sentences(v: str, chance: float | None, months: int, low, high, miss_pct: int, is_limited: bool) -> list[dict]:
    if chance is None:
        return [render("why_none")]
    c, line = round(chance * 100), {"Buy": BUY_AT, "Watch": BUY_AT, "Weak": SELL_AT, "Sell": SELL_AT}.get(v, BUY_AT)
    pct = f"{round(line * 100)}"
    out = [render({"Buy": "why_buy", "Watch": "why_watch", "Hold": "why_hold", "Weak": "why_weak"}.get(v, "why_sell"),
                  chance=str(c), months=str(months), line=pct)]
    out.append(render("wrong_range", low=f"{low:,.0f}", high=f"{high:,.0f}", months=str(months)))
    out.append(render("wrong_odds", miss=str(miss_pct)))
    out.append(render("could_rise", high=f"{high:,.0f}"))
    if v in ("Watch", "Hold", "Weak"):
        out.append(render("buy_if", line=pct if v != "Weak" else str(round(BUY_AT * 100))))
    out.append(render("sell_if", low=f"{low:,.0f}"))
    if is_limited:
        out.append(render("limited"))
    return out


def make_calls(results: list[dict], report: dict, day: date, past: list[dict], note: dict[int, float]) -> list[dict]:
    """One call row per stock and horizon, built from the mechanical results (not yet checked: `check` holds back)."""
    rows = []
    for h, name in HORIZONS.items():
        rep = report.get("horizons", {}).get(str(h), {})
        cases, rate = int(rep.get("n_test", 0)), rep.get("hit_rate")
        for r in results:
            chance = r.get(f"chance_{name}")
            low, high = r.get(f"low_{name}"), r.get(f"high_{name}")
            v = verdict(chance)
            lim = limited(cases, rate, note.get(h))
            n, beat = similar(past, v, chance, h) if chance is not None else (0, 0)
            miss = round((1 - chance) * 100) if chance is not None else 0
            sent = sentences(v, chance, h // 21, low or 0, high or 0, miss, lim) if (low and high) or chance is None else \
                [render("why_none")]
            rows.append({"id": f"{r['exchange']}:{r['symbol']}:{day.isoformat()}:{h}", "symbol": r["symbol"],
                         "exchange": r["exchange"], "made_on": day.isoformat(), "verdict": v, "chance": chance,
                         "horizon_days": h, "base_cases": cases, "base_rate": rate, "sell_line": SELL_AT, "buy_line": BUY_AT,
                         "could_rise_to": high, "would_buy_at": None, "sell_at_once_at": low, "limited": lim,
                         "sentences_json": json.dumps(sent, ensure_ascii=False, separators=(",", ":")),
                         "similar_n": n, "similar_beat": beat, "model_version": MODEL_VERSION})
    return rows


def check(row: dict) -> str | None:
    """The first reason a call is held back (mirror of the contract's callRowCheck, C-170-1)."""
    if row["verdict"] != "No view yet":
        c = row["chance"]
        if not isinstance(c, (int, float)):
            return "a call with a view carries a chance"
        if c < CHANCE_MIN or c > CHANCE_MAX:
            return "chance outside 5% to 95%"
        if row["base_cases"] < BASE_CASES_MIN:
            return "base rate rests on fewer than 30 cases"
    if not row.get("horizon_days"):
        return "no horizon"
    s = json.loads(row["sentences_json"])
    if any(not re.search("[ঀ-৿]", x["bn"]) for x in s):
        return "a sentence has no Bengali"
    if row["limited"] and not any("limited evidence" in x["en"].lower() for x in s):
        return 'a thin or moved bucket needs "limited evidence" in the text'
    return None


def screen_and_hold(rows: list[dict]) -> tuple[list[dict], list[tuple[str, str]]]:
    ok, held = [], []
    for r in rows:
        why = check(r)
        (held.append((r["id"], why)) if why else ok.append(r))
    return ok, held


def run(ctx, results: list[dict] | None = None, report: dict | None = None, past: list[dict] | None = None,
        note: dict | None = None) -> str:
    day = ctx.range.end
    if results is None:
        results, report = _live_mechanical()
    if past is None:
        past = ctx.client._ok("/api/calls/scored", None, "GET").get("rows", [])
    note = backtest_note(Path("docs/backtest.md")) if note is None else note
    rows = make_calls(results, report or {}, day, past, note)
    ok, held = screen_and_hold(rows)
    for rid, why in held[:20]:
        ctx.progress.line(f"call {rid} held back: {why}", "fail")
    if rows and len(held) / len(rows) > HELD_LIMIT:
        raise RuntimeError(f"{len(held)} of {len(rows)} calls held back, over the limit")
    out = {"written": 0, "ignored": 0}
    for i in range(0, len(ok), 500):
        r = ctx.client._ok("/api/calls/publish", {"rows": ok[i:i + 500]})
        out["written"] += r["written"]
        out["ignored"] += r["ignored"]
    ctx.publish("calls_runs", [{"id": str(day), "day": str(day), "written": out["written"], "held_back": len(held)}],
                source="mechanical forecast", as_of=str(day))
    return f"{out['written']} calls added, {out['ignored']} already there, {len(held)} held back"


def _live_mechanical() -> tuple[list[dict], dict]:
    import json as _j

    from stockpilot.sources.http import fetch
    base = "https://github.com/stockpilot-hq/stockpilot-engine/releases/download/mechanical-latest/"
    listing = _j.loads(fetch("https://api.github.com/repos/stockpilot-hq/stockpilot-engine/releases/tags/mechanical-latest"))
    days = sorted(a["name"][:-5] for a in listing["assets"] if re.fullmatch(r"20\d\d-\d\d-\d\d\.json", a["name"]))
    if not days:
        raise RuntimeError("no mechanical forecast file yet")
    doc = _j.loads(fetch(base + days[-1] + ".json"))
    try:
        rep = _j.loads(fetch(base + f"report-{days[-1]}.json"))
    except Exception:  # noqa: BLE001 - without its report there is no base rate, and every call is held back
        rep = {}
    return doc["results"], rep
