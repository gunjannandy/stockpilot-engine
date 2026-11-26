"""T20: the Saturday review. A reviewer that is not the forecaster reads the scored calls and proposes at most three prompt or
input changes, each with its evidence. Code checks every claim against the dossier (documents over claims), drops what breaks
a rule, and files what is left as asks that wait for the owner's Approve in the existing feedback flow. This module changes
nothing the forecaster reads: a proposal is words in a row until the owner approves it and a ticket builds it. The newest
three months stay out of the dossier, so the reviewer cannot tune to calls it will be scored on next. The forecaster modules
never import this one (a test checks)."""
import json
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from stockpilot import house_rules, trackrecord
from stockpilot.forecast_form import ADJUST_AREAS, ITEM_CAP
from stockpilot.jobrun import JobFailed
from stockpilot.modeljson import json_in

PROMPT = Path(__file__).resolve().parents[2] / "prompts" / "weekly_review.md"
MAX_PROPOSALS = 3
HOLDOUT_DAYS = 90
KINDS = {"lower_cap", "drop_area", "change_input", "prompt_line"}
PROMPT_TARGETS = {"forecast_form"}
IST = timezone(timedelta(hours=5, minutes=30))
BN_WAITING = "সাপ্তাহিক পর্যালোচনার একটি প্রস্তাব আছে, আপনার অনুমোদনের অপেক্ষায়।"


def dossier(calls: list[dict], rows: list[dict], today: date, holdout_days: int = HOLDOUT_DAYS) -> dict:
    """What the reviewer reads: per area how many scored 3-month calls used it, the average points, how often the call went
    the way the adjustment pushed, and the Brier of the final chance against the starting one. Calls made inside the
    holdout (the newest three months) are left out."""
    cut = today - timedelta(days=holdout_days)
    scored = [r for r in rows if r["horizon"] == "3m" and r["made_on"] < cut]
    base_by_key = {(c["symbol"], c["exchange"], c["made_on"]): c for c in calls}
    areas: dict[str, dict] = {}
    for area in sorted(ADJUST_AREAS):
        used = []
        for r in scored:
            pts = sum(a["points"] for a in r["adjustments"] if a["area"] == area and a["horizon"] == "m3")
            if any(a["area"] == area and a["horizon"] == "m3" for a in r["adjustments"]):
                used.append((pts, r))
        if not used:
            continue
        up = [r for p, r in used if p > 0]
        down = [r for p, r in used if p < 0]
        areas[area] = {
            "n": len(used), "avg_points": sum(p for p, _ in used) / len(used),
            "up_n": len(up), "up_hit_rate": trackrecord._mean([r["beat"] for r in up]),
            "down_n": len(down), "down_hit_rate": trackrecord._mean([1 - r["beat"] for r in down]),
            "brier_final": trackrecord._mean([r["brier"] for _, r in used]),
            "brier_base": trackrecord._mean([r["base_brier"] for _, r in used])}
    return {"as_of": today.isoformat(), "holdout_from": cut.isoformat(), "scored_3m": len(scored), "areas": areas,
            "calls": [{"symbol": r["symbol"], "made_on": r["made_on"].isoformat(), "route": r["route"], "call": r["call"],
                       "chance_3m": r["chance"], "beat": r["beat"], "adjustments": r["adjustments"],
                       "model": base_by_key.get((r["symbol"], r["exchange"], r["made_on"]), {}).get("model")} for r in scored]}


def prompt(d: dict) -> str:
    return PROMPT.read_text().strip() + "\n\nDossier of scored calls:\n" + json.dumps(d, default=str, indent=1)


def _parse(answer) -> list[dict]:
    got = json_in(answer)
    if not isinstance(got, dict) or not isinstance(got.get("proposals"), list):
        raise ValueError("no proposals list")
    return got["proposals"]


def _check(p, d: dict) -> str | None:
    """The reason a proposal is dropped, or None."""
    if not isinstance(p, dict):
        return "A proposal was not an object."
    kind, target, ev = p.get("kind"), p.get("target"), p.get("evidence")
    if kind not in KINDS:
        return f"A proposal had the kind {kind!r}; it must be one of {sorted(KINDS)}."
    if not str(p.get("change") or "").strip() or not str(p.get("why") or "").strip():
        return "A proposal had no change or no reason."
    if not isinstance(ev, dict) or set(ev) != {"area", "n"}:
        return "A proposal had no evidence of the form {area, n}."
    if ev["area"] not in d["areas"]:
        return f"The evidence area {ev['area']!r} is not in the dossier."
    if ev["n"] != d["areas"][ev["area"]]["n"]:
        return f"The evidence n={ev['n']} does not match the dossier ({d['areas'][ev['area']]['n']})."
    if kind == "prompt_line":
        if target not in PROMPT_TARGETS:
            return f"A prompt line must target one of {sorted(PROMPT_TARGETS)}."
        if not house_rules.acceptable(p["change"]):
            return "A prompt line was about money, numbers or the rules, or too long."
        return None
    if target not in d["areas"] or target != ev["area"]:
        return f"The target {target!r} is not an area in the dossier, or is not the evidence area."
    if kind == "lower_cap":
        v = p.get("new_value")
        if not isinstance(v, int) or isinstance(v, bool) or not 1 <= v < ITEM_CAP:
            return f"A cap may only go down, to a whole number from 1 to {ITEM_CAP - 1}."
    return None


def propose(d: dict, model) -> dict:
    """Ask the reviewer; keep at most three checked proposals, strongest first; say why anything was dropped."""
    try:
        raw = _parse(model.ask(prompt(d)))
    except (ValueError, TypeError) as err:
        return {"proposals": [], "dropped": [f"We could not read the reviewer's answer ({err})."]}
    kept, dropped = [], []
    for p in raw:
        why = _check(p, d)
        if why:
            dropped.append(why)
        elif len(kept) >= MAX_PROPOSALS:
            dropped.append(f"Only three are kept (more than three came back); kept the first three and dropped the {p['kind']} for {p['target']}.")
        else:
            kept.append({**{k: p[k] for k in ("kind", "target", "change", "why", "evidence")}, "change_bn": str(p.get("change_bn") or "").strip() or None,
                         "new_value": p.get("new_value"), "status": "proposed"})
    return {"proposals": kept, "dropped": dropped}


def rows(proposals: list[dict], review_id: str, now: str) -> tuple[dict | None, list[dict]]:
    """The `feedback` row (a message from the owner's own system) and the `asks` rows of the live contract. Every ask waits
    for Approve; the existing Approve button turns an approved ask into a ticket."""
    if not proposals:
        return None, []
    fb = {"id": review_id, "person": "owner", "text": "Weekly review: " + "; ".join(p["change"] for p in proposals),
          "status": "understood", "created_at": now}
    asks = []
    for i, p in enumerate(proposals, 1):
        ev = p["evidence"]
        asks.append({"id": f"{review_id}_a{i}", "feedback_id": review_id,
                     "original": f"{p['why']} (area {ev['area']}, {ev['n']} scored calls)", "line_en": p["change"],
                     "line_bn": p.get("change_bn") or BN_WAITING, "tag": "forecast", "size": "small",
                     "plan": f"{p['kind']} on {p['target']}: {p['change']}", "route": "owner_approval",
                     "status": "waiting_for_approval", "not_meant": False, "issue_number": None, "updated_at": now})
    return fb, asks


def _plural(n: int) -> str:
    return f"{n} proposal{'s' if n != 1 else ''}"


def handler(load, save, today):
    """Job handler for `weekly_review`. `load()` gives (calls, prices, nifty, news); `save(feedback_row, ask_rows, doc)`
    stores the record document and the asks; `today()` is a date. With nothing scored yet it saves the record and spends no
    model call."""
    def run(ctx):
        ctx.progress("Reading the calls and prices", "কল আর দাম পড়া হচ্ছে")
        calls, prices, nifty, news = load()
        day = today()
        rows_ = trackrecord.score_calls(calls, prices, nifty, day)
        doc = {"as_of": day.isoformat(), "track_record": trackrecord.summary(rows_), "news_buys": trackrecord.news_buys(rows_, news),
               "proposals": [], "dropped": []}
        ctx.progress(f"Scored {len(rows_)} call results at 1, 3 and 6 months", f"{len(rows_)}টি ফল নম্বর দেওয়া হল")
        d = dossier(calls, rows_, day)
        if not d["scored_3m"]:
            save(None, [], doc)
            return "Nothing to review yet: no call has a finished 3-month result outside the newest three months"
        model = ctx.model
        ctx.progress("Asking the reviewer", "পর্যালোচককে জিজ্ঞাসা করা হচ্ছে")
        got = propose(d, model)
        doc.update(proposals=got["proposals"], dropped=got["dropped"])
        now = datetime.now(IST).replace(microsecond=0).isoformat()
        fb, asks = rows(got["proposals"], f"review_{day.isoformat()}", now)
        save(fb, asks, doc)
        if not got["proposals"]:
            return "No changes proposed this week"
        return f"{_plural(len(asks))} waiting for Approve"
    return run
