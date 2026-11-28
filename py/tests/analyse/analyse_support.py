"""Shared stand-ins for the Analyse tests and checks: made-up public inputs, a model answer, a Worker with the Analyse routes."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime"))
from fake_runtime_worker import KEY, FakeRuntimeWorker  # noqa: E402

from stockpilot.io import Door  # noqa: E402

DAY = "2026-11-28"


def made_up_inputs():
    """Public data for a made-up stock: facts, 300 daily rows rising a little, one news impact row."""
    history = [{"date": f"d{i}", "close": 100 + i * 0.2} for i in range(300)]
    facts = {"symbol": "ABC", "name": "Abc Ltd", "sector": "Metals", "pe": 12.0, "pe_sector": 20.0, "pb": 1.5,
             "roe_pct": 18.0, "debt_to_equity": 0.2, "profit_growth_yoy_pct": 14.0, "pledge_pct": 0.0}
    news = [{"id": "n1", "title": "Plant expansion approved", "direction": "good", "size": "medium",
             "why_en": "Adds 20 percent capacity"}]
    return {"facts": facts, "history": history, "news": news}


def good_answer(**over):
    form = {"call": "buy", "chance_pct": 62,
            "summary_en": "Cheap against its sector with a strong return on equity of 18.",
            "summary_bn": "সেক্টরের তুলনায় সস্তা, ইক্যুইটিতে রিটার্ন ১৮।",
            "reasons": [{"text_en": "Its P/E of 12 is below the sector's 20.", "text_bn": "এর P/E ১২, সেক্টরের ২০-এর নিচে।",
                         "evidence": ["fact:pe", "fact:pe_sector"]}],
            "risks": [{"text_en": "Metal prices can fall.", "text_bn": "ধাতুর দাম পড়তে পারে।"}]}
    return {**form, **over}


class AnalyseWorker(FakeRuntimeWorker):
    def __init__(self, inputs=None, **kw):
        super().__init__(**kw)
        self.inputs, self.calls_stored = inputs or made_up_inputs(), []

    def transport(self, method, url, headers, body):
        route = "/" + url.split("/", 3)[3]
        if route.startswith("/api/analyse/inputs/"):
            return 200, self.inputs
        if route == "/api/analyse/call":
            self.calls_stored.append(json.loads(body))
            return 200, {"ok": True}
        return super().transport(method, url, headers, body)


def door(worker):
    return Door("https://x.invalid", KEY, worker.transport)


def answer_for(brief, call=None, **over):
    """A valid, bilingual answer for any brief: it cites the code's own number and one piece of the brief's evidence."""
    code = brief["code"]
    c = code["chance_pct"]
    form = {"call": call or code["call"], "chance_pct": c,
            "summary_en": f"The code puts the chance at {c} out of 100.",
            "summary_bn": f"কোডের হিসাবে সম্ভাবনা {c}, ১০০-এর মধ্যে 100।",
            "reasons": [{"text_en": f"The chance is {c}.", "text_bn": f"সম্ভাবনা {c}।", "evidence": brief["evidence"][:1]}],
            "risks": [{"text_en": "Prices can fall.", "text_bn": "দাম পড়তে পারে।"}]}
    if form["call"] != code["call"]:
        form["moved_because"] = "The evidence points the other way."
    return json.dumps({**form, **over}, ensure_ascii=False)


FUND = {"id": "f1", "name": "Made Up Flexi Fund", "category": "Equity Scheme - Flexi Cap Fund", "ter": 0.6, "aum_cr": 12000,
        "r1": 14.0, "r3": 16.5, "r5": 15.0, "cat_r1": 11.0, "cat_r3": 13.0, "cat_r5": 12.0, "category_n": 30, "max_fall": -32.0,
        "roll_min": -8.0, "roll_median": 14.0, "roll_max": 40.0, "roll_loss_share": 12.0}
FUND_CALL = {"id": "f1", "kind": "call", "call": "buy", "rank": 2, "of": 30, "quartile": 1, "chance": 0.64, "cases": 90,
             "periods": 6, "avg_excess": 1.8, "reasons": "", "caveat": "Funds alive today only"}


class FundWorker(FakeRuntimeWorker):
    def __init__(self, fund=FUND, call=FUND_CALL, **kw):
        super().__init__(**kw)
        self.fund, self.call, self.calls_stored = fund, call, []

    def transport(self, method, url, headers, body):
        route = "/" + url.split("/", 3)[3]
        if route.startswith("/api/fundcall/inputs/"):
            return 200, {"fund": self.fund, "call": self.call}
        if route == "/api/fundcall/call":
            self.calls_stored.append(json.loads(body))
            return 200, {"ok": True}
        return super().transport(method, url, headers, body)
