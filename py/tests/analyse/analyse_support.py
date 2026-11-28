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
