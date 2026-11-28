"""The post-mortem Job: a missed call, scored at three months, gets one short post-mortem row (English and Bengali).

The Worker works out which calls missed and are due (`/api/postmortem/due`); this Job writes one row per call through
`/api/postmortem/row`, shown on Record. Public data only: the call, how the stock and the Nifty moved, and public news.
A model answer that fails its checks, or no model, leaves a code-written line, so a missed call always gets its row."""
import json
import re

from stockpilot import reasoning
from stockpilot.jobs.analyse.answer import BENGALI, LATIN_DIGITS
from stockpilot.jobs.analyse.brief import check_public
from stockpilot.model import client as model_client
from stockpilot.modeljson import json_in
from stockpilot.prompts import load
from stockpilot.runtime import JobContext

KIND = "postmortem"
CAUSES = ("thesis_wrong", "risk_hit", "news_after", "market", "unknown")
MAX_PER_RUN = 10


def build(due: dict) -> dict:
    """The brief for one due call (a row of `/api/postmortem/due`)."""
    call = {k: due[k] for k in ("symbol", "day", "call", "chance_pct", "summary_en") if due.get(k) is not None}
    call["reasons"] = [r.get("text_en", "") for r in due.get("reasons") or []]
    call["risks"] = [r.get("text_en", "") for r in due.get("risks") or []]
    result = {k: due[k] for k in ("stock_pct", "nifty_pct", "excess_pct", "end_day")}
    news = [{"id": f"news:{i}", "title": n.get("title", ""), "direction": n.get("direction"), "why": n.get("why_en", "")}
            for i, n in enumerate((due.get("news_after") or [])[:6])]
    evidence = ["call", "result"] + [f"risk:{i}" for i in range(len(call["risks"]))] + \
               [f"reason:{i}" for i in range(len(call["reasons"]))] + [n["id"] for n in news]
    brief = {"as_of": due["end_day"], "call": call, "result": result, "news_after": news, "evidence": evidence}
    check_public(brief)
    return brief


def verify(text, brief: dict) -> tuple[dict | None, list[str]]:
    try:
        form = json_in(text)
    except ValueError as err:
        return None, [f"no JSON in the answer: {err}"]
    if not isinstance(form, dict):
        return None, ["the answer is not an object"]
    errs = []
    if form.get("cause") not in CAUSES:
        errs.append(f"cause is {form.get('cause')!r}")
    en, bn = form.get("why_en"), form.get("why_bn")
    if not isinstance(en, str) or not en.strip():
        errs.append("no English")
    elif not isinstance(bn, str) or not BENGALI.search(bn):
        errs.append("no Bengali")
    else:
        gone = [n for n in reasoning.numbers(en) if n not in reasoning.numbers(bn.translate(LATIN_DIGITS))]
        if gone:
            errs.append(f"the Bengali drops the numbers {gone}")
        pool = reasoning.number_pool(brief) | {"100"}
        errs += [f"the number {n} is not in the brief" for n in dict.fromkeys(reasoning.numbers(en)) if n not in pool]
    ev = form.get("evidence")
    if not isinstance(ev, list):
        errs.append("evidence is not a list")
    else:
        errs += [f"evidence {i!r} is not in the brief" for i in ev if i not in brief["evidence"]]
        if not ev and form.get("cause") != "unknown":
            errs.append("a cause without evidence")
    return (None if errs else form), errs


def code_row(brief: dict) -> dict:
    """The line that stands without a model: what was called, how far it missed, and the risks the call named."""
    c, r = brief["call"], brief["result"]
    miss = abs(r["excess_pct"])
    word = "ahead of" if r["excess_pct"] > 0 else "behind"
    en = f"{c['call'].capitalize()} called on {c['day']}: the stock ended {miss:g} points {word} the Nifty 50 over three months."
    bn = f"{c['day']} তারিখের কল: তিন মাসে শেয়ারটি নিফটি ৫০-এর থেকে {miss:g} পয়েন্ট {'এগিয়ে' if r['excess_pct'] > 0 else 'পিছিয়ে'} শেষ করেছে।"
    return {"cause": "unknown", "why_en": en, "why_bn": bn, "evidence": ["result"], "source": "code", "model": None}


def decide(brief: dict, client, *, runner=None) -> dict:
    rejected: list[str] = []

    def go(prompt: str, model: str) -> str:
        text = (runner or model_client.run_claude)(prompt, model)
        form, errs = verify(text, brief)
        if errs:
            rejected.extend(errs)
            raise ValueError("; ".join(errs)[:300])
        return text
    prompt = load("postmortem") + "\n\nBRIEF:\n" + json.dumps(brief, ensure_ascii=False, separators=(",", ":"))
    row = code_row(brief)
    try:
        got = model_client.ask(KIND, prompt, client=client, runner=go)
        form, errs = verify(got.text, brief)
        if form:
            return {"cause": form["cause"], "why_en": form["why_en"], "why_bn": form["why_bn"], "evidence": form["evidence"],
                    "source": "model", "model": got.model}
    except (ValueError, model_client.OverDailyCap, model_client.NoModelToken, RuntimeError):
        pass
    return row


def run(ctx: JobContext, *, due: dict | None = None, runner=None) -> str:
    due = due if due is not None else ctx.client._ok("/api/postmortem/due", None, "GET")
    rows = due.get("calls") or []
    written = 0
    for item in rows[:MAX_PER_RUN]:
        if not re.match(r"^[A-Z0-9][A-Z0-9&-]{0,19}$", str(item.get("symbol", ""))):
            continue
        brief = build(item)
        row = decide(brief, ctx.client, runner=runner)
        ctx.client._ok("/api/postmortem/row", {"call_key": item["key"], "symbol": item["symbol"], "day": item["day"],
                                                "call": item["call"], "excess_pct": item["excess_pct"], **row})
        written += 1
        ctx.progress.line(f"{item['symbol']}: post-mortem written ({row['source']})", "ok")
    return f"{written} post-mortems written, {max(0, len(rows) - MAX_PER_RUN)} left for the next run"
