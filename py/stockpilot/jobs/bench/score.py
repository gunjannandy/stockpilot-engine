"""Scoring the Analyse bench: form checks, hits against what happened, agreement between two models, and the red rule.

A case is one past public brief with its outcome (`beat`: the stock beat the Nifty over the next three months). A `buy`
is a hit when it beat, an `avoid` when it did not; `watch` is not scored. The code-only call is scored the same way so a
model has to be at least as good as plain code."""
import hashlib
import json
from pathlib import Path

from stockpilot.jobs.analyse import answer as A
from stockpilot.model.kinds import model_for
from stockpilot.prompts import load

FORM_MIN = 0.95        # share of answers that pass every check (contract BENCH_FORM_MIN)
AGREE_MIN = 0.80       # share of cases where Haiku's call equals Sonnet's (BENCH_VERDICT_MIN)
SLACK = 0.05           # a model may trail the code-only hit rate by this much before the bench is red
MIN_DECIDED = 5
HERE = Path(__file__).parent
METHOD_FILES = ("../analyse/brief.py", "../analyse/answer.py")


def cases() -> list[dict]:
    return json.loads((HERE / "cases.json").read_text())


def fingerprint(model: str | None = None) -> str:
    """Changes when the prompt, the model, the method code or the cases change: the bench runs again when it does."""
    h = hashlib.sha256()
    h.update(load("analyse").encode())
    h.update((model or model_for("analyse")).encode())
    for f in METHOD_FILES:
        h.update((HERE / f).read_bytes())
    h.update((HERE / "cases.json").read_bytes())
    return h.hexdigest()[:16]


def _hit(call: str | None, beat: bool) -> bool | None:
    return None if call not in ("buy", "avoid") else (call == "buy") == beat


def hit_rate(calls: dict[str, str | None], items: list[dict]) -> tuple[float | None, int]:
    hits = [_hit(calls.get(c["id"]), c["outcome"]["beat"]) for c in items]
    decided = [h for h in hits if h is not None]
    return (sum(decided) / len(decided) if decided else None), len(decided)


def code_calls(items: list[dict]) -> dict[str, str]:
    return {c["id"]: c["brief"]["code"]["call"] for c in items}


def score_answers(items: list[dict], texts: dict[str, str | None]) -> dict:
    """`texts`: case id -> the model's raw answer (None when it gave none)."""
    calls: dict[str, str | None] = {}
    ok = 0
    problems: dict[str, list[str]] = {}
    for c in items:
        text = texts.get(c["id"])
        v = A.verify(text, c["brief"]) if text else A.Verdict(False, None, ["no answer"])
        calls[c["id"]] = v.form["call"] if v.ok else None
        ok += v.ok
        if not v.ok:
            problems[c["id"]] = v.reasons[:3]
    rate, decided = hit_rate(calls, items)
    code_rate, _ = hit_rate(code_calls(items), items)
    return {"n": len(items), "form_ok": ok, "form_rate": round(ok / len(items), 3), "hit_rate": rate, "decided": decided,
            "code_hit_rate": code_rate, "calls": calls, "problems": problems}


def agreement(a: dict[str, str | None], b: dict[str, str | None]) -> float:
    ids = list(a)
    return round(sum(1 for i in ids if a[i] is not None and a[i] == b.get(i)) / len(ids), 3)


def is_red(s: dict) -> list[str]:
    """Why the bench is red, empty when green."""
    why = []
    if s["form_rate"] < FORM_MIN:
        why.append(f"form checks {s['form_rate']:.0%} are under {FORM_MIN:.0%}")
    if s["hit_rate"] is not None and s["code_hit_rate"] is not None and s["decided"] >= MIN_DECIDED \
            and s["hit_rate"] < s["code_hit_rate"] - SLACK:
        why.append(f"hit rate {s['hit_rate']:.0%} trails the code-only {s['code_hit_rate']:.0%}")
    return why


def comparison(haiku: dict, sonnet: dict) -> dict:
    """The Haiku comparison: Haiku keeps forecasts only if it passes both lines, else Sonnet does."""
    agree = agreement(haiku["calls"], sonnet["calls"])
    passed = haiku["form_rate"] >= FORM_MIN and agree >= AGREE_MIN
    return {"form_rate": haiku["form_rate"], "agreement": agree, "passed": passed,
            "forecast_model": "haiku" if passed else "sonnet"}
