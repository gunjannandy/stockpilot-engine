"""The fund Analyse brief: public fund facts and the code's call from past NAV history, nothing about anyone's holdings.

Built from the `funds` row and the `fund_calls` row the Worker serves to Jobs. The same lock as the stock brief refuses any
private-looking key; the call card adds switching cost and tax lines in the browser, on the device."""
import json

from stockpilot.jobs.analyse.brief import HORIZON_DAYS, check_public

CALLS = ("buy", "watch")
FACT_KEYS = ("ter", "ter_regular", "aum_cr", "r1", "r3", "r5", "cat_r1", "cat_r3", "cat_r5", "category_n", "max_fall",
             "roll_min", "roll_median", "roll_max", "roll_loss_share")
CALL_KEYS = ("rank", "of", "quartile", "cases", "periods", "avg_excess", "reasons", "caveat")


def code_view(call_row: dict | None) -> dict:
    """The code's call: the published one, or Watch with a 50% chance when the fund has no measured call."""
    if not call_row or call_row.get("call") not in CALLS:
        return {"call": "watch", "chance_pct": 50}
    chance = call_row.get("chance")
    return {"call": call_row["call"], "chance_pct": round(100 * chance) if chance is not None else 50}


def build(fund_id: str, day: str, *, fund: dict | None, call_row: dict | None) -> dict:
    fund, call_row = fund or {}, call_row or {}
    facts = {k: fund[k] for k in FACT_KEYS if fund.get(k) is not None}
    measured = {k: call_row[k] for k in CALL_KEYS if call_row.get(k) not in (None, "")}
    evidence = [f"fact:{k}" for k in facts] + [f"call:{k}" for k in measured]
    brief = {"as_of": day, "fund": fund_id, "name": fund.get("name", ""), "category": fund.get("category") or "",
             "horizon_days": 4 * HORIZON_DAYS, "calls": list(CALLS), "code": code_view(call_row), "facts": facts,
             "call_basis": measured, "evidence": evidence,
             "gaps": [k for k in FACT_KEYS if k not in facts]}
    check_public(brief)
    return brief


def render(brief: dict, prompt: str) -> str:
    check_public(brief)
    return prompt + "\n\nBRIEF:\n" + json.dumps(brief, ensure_ascii=False, separators=(",", ":"))
