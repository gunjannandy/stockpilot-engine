"""Check a model's Analyse answer before it is stored (v2 verify check 10, kept).

Rejected when: it is not the form; any sentence has no Bengali or loses a number in Bengali; it cites a number that is not
in the brief; it cites evidence the brief does not hold; or it moves the call away from the code's view without citing
evidence. A rejected answer is never stored and the code-only call stands."""
import re
from dataclasses import dataclass, field

from stockpilot import reasoning
from stockpilot.modeljson import json_in

CALLS = ("buy", "watch", "avoid")
BENGALI = re.compile(r"[ঀ-৿]")
LATIN_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
MAX_REASONS = MAX_RISKS = 3


@dataclass
class Verdict:
    ok: bool
    form: dict | None = None
    reasons: list[str] = field(default_factory=list)


def code_only(brief: dict) -> dict:
    """The call that stands when the model's answer is missing or rejected."""
    return {"call": brief["code"]["call"], "chance_pct": brief["code"]["chance_pct"], "source": "code"}


def _pairs(form: dict):
    yield "summary", form.get("summary_en"), form.get("summary_bn")
    for r in form.get("reasons") or []:
        yield "reason", r.get("text_en"), r.get("text_bn")
    for r in form.get("risks") or []:
        yield "risk", r.get("text_en"), r.get("text_bn")


def check_shape(form, calls=CALLS) -> list[str]:
    if not isinstance(form, dict):
        return ["the answer is not an object"]
    errs = []
    if form.get("call") not in calls:
        errs.append(f"call is {form.get('call')!r}, not one of {list(calls)}")
    c = form.get("chance_pct")
    if isinstance(c, bool) or not isinstance(c, (int, float)) or not 0 <= c <= 100:
        errs.append("chance_pct is not a number from 0 to 100")
    for k in ("reasons", "risks"):
        if not isinstance(form.get(k), list) or len(form[k]) > MAX_REASONS:
            errs.append(f"{k} is not a list of at most {MAX_REASONS}")
    if not errs:
        for r in form["reasons"]:
            if not isinstance(r, dict) or not isinstance(r.get("evidence"), list):
                errs.append("a reason has no evidence list")
        if any(not isinstance(r, dict) for r in form["risks"]):
            errs.append("a risk is not an object")
    return errs


def check_bengali(form: dict) -> list[str]:
    """English and Bengali come in one answer: a pair with no Bengali, or Bengali that loses a number, rejects it."""
    errs = []
    for label, en, bn in _pairs(form):
        if not isinstance(en, str) or not en.strip():
            errs.append(f"a {label} has no English")
        elif not isinstance(bn, str) or not BENGALI.search(bn):
            errs.append(f"a {label} has no Bengali")
        else:
            gone = [n for n in reasoning.numbers(en) if n not in reasoning.numbers(bn.translate(LATIN_DIGITS))]
            if gone:
                errs.append(f"the Bengali of a {label} drops the numbers {gone}")
    return errs


def check_numbers(form: dict, brief: dict) -> list[str]:
    pool = reasoning.number_pool(brief) | {"100"}
    errs = []
    for label, en, _ in _pairs(form):
        for n in reasoning.numbers(en or ""):
            if n not in pool:
                errs.append(f"the number {n} in a {label} is not in the brief")
    return list(dict.fromkeys(errs))


def check_evidence(form: dict, brief: dict) -> list[str]:
    known, errs = set(brief["evidence"]), []
    cited = [i for r in form["reasons"] for i in r["evidence"]]
    errs += [f"evidence {i!r} is not in the brief" for i in dict.fromkeys(cited) if i not in known]
    if form["call"] != brief["code"]["call"]:
        good = [i for i in cited if i in known]
        if not good or not str(form.get("moved_because") or "").strip():
            errs.append(f"the call moved from {brief['code']['call']} to {form['call']} without cited evidence")
    return errs


def verify(text, brief: dict) -> Verdict:
    """`text`: the model's raw answer. Returns the checked form or the plain reasons it was rejected."""
    try:
        form = json_in(text)
    except ValueError as err:
        return Verdict(False, None, [f"no JSON in the answer: {err}"])
    errs = check_shape(form, tuple(brief.get("calls") or CALLS))
    if errs:
        return Verdict(False, None, errs)
    errs = check_bengali(form) + check_numbers(form, brief) + check_evidence(form, brief)
    return Verdict(not errs, form if not errs else None, errs)


def final_call(form: dict) -> dict:
    return {"call": form["call"], "chance_pct": round(form["chance_pct"]), "source": "model"}
