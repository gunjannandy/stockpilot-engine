"""The Analyse Job: one stock, public data only, a call with English and Bengali from one model call.

The button starts it through the Job runtime. Inputs come from the Worker's Job-only read of public facts, daily history
and news impact; the brief carries no holding or tax field (the browser adds those lines on the device). The model's answer
is checked before it is stored; a rejected, refused or missing answer leaves the code-only call standing."""
import re

from stockpilot.model import client as model_client
from stockpilot.prompts import load
from stockpilot.runtime import JobContext

from . import answer as A
from .brief import build, render

KIND = "analyse"
SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9&-]{0,19}$")


class Rejected(RuntimeError):
    """The model answered but the answer failed its checks; nothing is stored."""


def _runner(brief: dict, rejected: list[str]):
    def go(prompt: str, model: str) -> str:
        text = model_client.run_claude(prompt, model)
        verdict = A.verify(text, brief)
        if not verdict.ok:
            rejected.extend(verdict.reasons)
            raise Rejected("; ".join(verdict.reasons)[:300])
        return text
    return go


def decide(brief: dict, client, *, runner=None) -> dict:
    """The row to store: the model's checked call, or the code-only call with the reason it stands."""
    rejected: list[str] = []
    row = {**A.code_only(brief), "summary_en": None, "summary_bn": None, "reasons": [], "risks": [], "model": None,
           "note": None}
    try:
        got = model_client.ask(KIND, render(brief, load("analyse")), client=client, runner=runner or _runner(brief, rejected))
        verdict = A.verify(got.text, brief)
        if verdict.ok:
            f = verdict.form
            return {**row, **A.final_call(f), "summary_en": f["summary_en"], "summary_bn": f["summary_bn"],
                    "reasons": f["reasons"], "risks": f["risks"], "model": got.model}
        rejected += verdict.reasons
    except Rejected:
        pass
    except model_client.OverDailyCap:
        row["note"] = model_client.NEXT_UPDATE_TOMORROW
    except model_client.NoModelToken:
        row["note"] = "no model token"
    except RuntimeError as err:
        row["note"] = f"model unavailable: {str(err)[:120]}"
    if rejected:
        row["note"] = "answer rejected: " + "; ".join(rejected)[:300]
    return row


def run(ctx: JobContext, *, inputs: dict | None = None, runner=None) -> str:
    symbol = ctx.subject.upper()
    if not SYMBOL.match(symbol):
        raise ValueError(f"not a stock symbol: {ctx.subject!r}")
    day = str(ctx.range.end)
    data = inputs if inputs is not None else ctx.client._ok(f"/api/analyse/inputs/{symbol}", None, "GET")
    brief = build(symbol, day, facts=data.get("facts"), history=data.get("history") or [], news=data.get("news") or [])
    ctx.progress.line("Public facts read, asking the model",
                      text_bn=None)
    row = decide(brief, ctx.client, runner=runner)
    ctx.client._ok("/api/analyse/call", {"symbol": symbol, "day": day, **row})
    ctx.progress.line(f"{symbol}: {row['call']} ({row['source']})", "ok" if row["source"] == "model" else "info")
    return f"{symbol} {row['call']}, {row['chance_pct']}%, from {row['source']}"
