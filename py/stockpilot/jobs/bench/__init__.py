"""The bench Job: scores the Analyse method on about 30 past public briefs with outcomes.

It runs on `main` only (protected `models` environment), and again whenever the prompt, the model, the method code or the
cases change (the fingerprint). Its first run is the Haiku comparison: Haiku and Sonnet answer every case, and Haiku keeps
forecasts only with at least 95% form checks and 80% agreeing verdicts; otherwise the report names Sonnet. A red run asks
the Worker to pause releases; a green run lifts a pause the bench itself set.

The bench talks to the model directly, one slot, one case at a time: it is main's own budget, not a press, so it does not
use a pane's daily gate."""
from stockpilot.model import client as model_client
from stockpilot.model.kinds import model_for
from stockpilot.prompts import load
from stockpilot.runtime import JobContext

from ..analyse.brief import render
from . import score

KIND = "bench"
REFERENCE = "sonnet"


def ask_all(items: list[dict], model: str, ask, progress=None) -> dict[str, str | None]:
    prompt = load("analyse")
    out: dict[str, str | None] = {}
    for n, c in enumerate(items, 1):
        try:
            out[c["id"]] = ask(render(c["brief"], prompt), model)
        except Exception:  # noqa: BLE001 - one failed ask is a missed case, not a dead bench
            out[c["id"]] = None
        if progress and n % 10 == 0:
            progress(f"{model}: {n} of {len(items)} cases asked")
    return out


def run(ctx: JobContext, *, ask=None) -> str:
    ask = ask or (lambda prompt, model: model_client.run_claude(prompt, model))
    items = score.cases()
    model = model_for("analyse")
    print_ = ctx.progress.line
    status = ctx.client._ok("/api/bench/status", None, "GET")
    fp = score.fingerprint(model)
    first = status.get("comparison") is None
    if status.get("fingerprint") == fp and not first:
        return "unchanged since the last bench run"
    mine = score.score_answers(items, ask_all(items, model, ask, print_))
    report = {"fingerprint": fp, "model": model, "scores": {k: v for k, v in mine.items() if k not in ("calls", "problems")},
              "problems": mine["problems"], "comparison": status.get("comparison"), "red": score.is_red(mine)}
    if first:
        ref = score.score_answers(items, ask_all(items, REFERENCE, ask, print_)) if model != REFERENCE else mine
        report["comparison"] = score.comparison(mine, ref)
    report["forecast_model"] = (report["comparison"] or {}).get("forecast_model", "haiku")
    ctx.client._ok("/api/bench/report", report)
    ctx.progress.line("red: " + "; ".join(report["red"]) if report["red"] else "green",
                      "fail" if report["red"] else "ok")
    return f"bench {'red' if report['red'] else 'green'}, form {mine['form_rate']:.0%}, forecasts on {report['forecast_model']}"
