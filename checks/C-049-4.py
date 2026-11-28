"""C-049-1 (data half): the list sections build from the screen dataset, each row with reasons in both languages."""
import json
import re

from stockpilot.jobs.lists import build
from stockpilot.jobs.lists import templates as T

AT = "2026-11-28T10:00:00+05:30"


def screen(n=40):
    rows = []
    for i in range(n):
        rows.append({"symbol": f"S{i:02d}", "exchange": "NSE", "industry": "A", "quality": 0.9 if i < 3 else 0.5, "value": 0.5,
                     "momentum": 0.05 if i >= n - 3 else 0.5, "risk": 0.5, "score": 1 - i / n, "rank": i + 1})
    rows.append({"symbol": "OUT", "exchange": "NSE", "industry": "", "quality": None, "value": None, "momentum": None,
                 "risk": None, "score": None, "rank": None, "excluded": "no industry"})
    return rows


def test_sections_and_reasons():
    calls = [{"symbol": "S05", "exchange": "NSE", "verdict": "Buy", "chance": 0.6}, {"symbol": "S06", "exchange": "NSE", "verdict": "Hold", "chance": 0.45}]
    rows = build(screen(), calls, [{"symbol": "S09", "move_pct": -4.2}], AT)
    by = {}
    for r in rows:
        by.setdefault(r["list"], []).append(r)
    assert [r["symbol"] for r in by["top10"]] == [f"S{i:02d}" for i in range(10)]
    assert [r["symbol"] for r in by["just_missed"]][:2] == ["S10", "S11"] and len(by["just_missed"]) == 10
    assert [r["symbol"] for r in by["has_view"]] == ["S05"]
    assert [r["symbol"] for r in by["falling"]] == ["S37", "S38", "S39"]
    assert by["busy_today"][0]["symbol"] == "S09"
    for r in rows:
        assert r["id"] == f"{r['list']}:{r['symbol']}" and r["updated_at"] == AT
        reasons = json.loads(r["reasons_json"])
        assert reasons and all(re.search("[ঀ-৿]", x["bn"]) for x in reasons)
    assert "quality_top" in {x["key"] for x in json.loads(by["top10"][0]["reasons_json"])}


def test_every_template_has_bengali_with_the_same_placeholders():
    for key, t in T.TEMPLATES.items():
        assert re.search("[ঀ-৿]", t["bn"]), key
        assert T.fields(t["en"]) == T.fields(t["bn"]), key
