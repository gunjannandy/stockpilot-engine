"""The fund Analyse Job: one fund, public data only, a buy or watch call with English and Bengali from one model call.

Same rules as stock Analyse: the answer is checked before it is stored (every number in the brief, Bengali beside every
English line, a moved call cites evidence); anything else leaves the code's call standing."""
import re

from stockpilot.jobs.analyse import answer as A
from stockpilot.model import client as model_client
from stockpilot.prompts import load
from stockpilot.runtime import JobContext

from .brief import build, render

KIND = "fundcall"
FUND_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9:_.-]{0,60}$")


class Rejected(RuntimeError):
    pass


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
    rejected: list[str] = []
    row = {**A.code_only(brief), "summary_en": None, "summary_bn": None, "reasons": [], "risks": [], "model": None,
           "note": None}
    try:
        got = model_client.ask(KIND, render(brief, load("fundcall")), client=client, runner=runner or _runner(brief, rejected))
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
    fund_id = ctx.subject
    if not FUND_ID.match(fund_id):
        raise ValueError(f"not a fund id: {fund_id!r}")
    day = str(ctx.range.end)
    data = inputs if inputs is not None else ctx.client._ok(f"/api/fundcall/inputs/{fund_id}", None, "GET")
    brief = build(fund_id, day, fund=data.get("fund"), call_row=data.get("call"))
    ctx.progress.line("Public fund facts read, asking the model")
    row = decide(brief, ctx.client, runner=runner)
    ctx.client._ok("/api/fundcall/call", {"fund": fund_id, "day": day, **row})
    ctx.progress.line(f"{fund_id}: {row['call']} ({row['source']})", "ok" if row["source"] == "model" else "info")
    return f"{fund_id} {row['call']}, {row['chance_pct']}%, from {row['source']}"
