"""Lane F1, analyst output: new optional `for`, `against` and `what_we_do_not_know` fields, checked against the brief."""
import json

from forecast_seed import AS_OF
from stockpilot.calls import runner
from test_forecast import db, fake_analyse, go, rows, template   # noqa: F401


def stored(db, symbol):
    return json.loads(db.execute("select reasons from calls where symbol = ? and made_on = ?", [symbol, AS_OF]).fetchone()[0])


def test_the_schema_accepts_the_new_optional_fields_and_does_not_require_them():
    schema = json.loads(runner.schema_path("analyst").read_text())
    item = schema["properties"]["items"]["items"]
    assert {"for", "against", "what_we_do_not_know"} <= set(item["properties"])
    assert not {"for", "against", "what_we_do_not_know"} & set(item["required"])
    good = {"market_view": "Calm.", "market_view_bn": "শান্ত।", "items": [{
        "symbol": "SBIN", "probability": 0.6, "moved_by": [], "risks": [], "summary": "s", "summary_bn": "s", "level_flag": None,
        "change_reason": None, "would_buy_if": None, "news_used": [],
        "for": [{"text": "Profit grew", "area": "growth", "news_used": [], "points": 2}], "against": [], "what_we_do_not_know": ["The next results"]}]}
    assert runner.schema_errors(good, schema) == []
    bad = json.loads(json.dumps(good))
    bad["items"][0]["for"] = "Profit grew"
    assert runner.schema_errors(bad, schema)


def test_good_items_are_stored_bad_numbers_are_dropped_and_unknowns_stay_off_the_site(db):
    seen = []

    def analyse(brief, role, runners, **kw):
        seen.append(brief)
        got = fake_analyse()(brief, role, runners)
        for it in got["decisions"]["items"]:
            if it["symbol"] == "WIPRO":
                close = next(s for s in brief["stocks"] if s["symbol"] == "WIPRO")["price"]["close"]
                it["for"] = [{"text": f"It trades at {close:g}, near the middle of its range", "area": "value", "news_used": [], "points": 1.5},
                             {"text": "Profit will jump 4321% next year", "area": "growth", "news_used": []}]
                it["against"] = [{"text": "Weak rupee could hurt margins", "area": "risk", "news_used": []}]
                it["what_we_do_not_know"] = ["Whether the next results disappoint"]
        return got
    out = go(db, analyse)
    r = stored(db, "WIPRO")
    assert [i["area"] for i in r["for"]] == ["value"] and r["for"][0]["weight"] == 1.5 and r["for"][0]["by"] == "analyst"
    assert r["against"][0]["text"] == "Weak rupee could hurt margins"
    assert r["unknowns"] == ["Whether the next results disappoint"]
    assert any("4321" in d for d in out["reasoning_dropped"])
    assert "for" not in stored(db, "ICICIBANK") or stored(db, "ICICIBANK")["for"] == []


def test_levels_hit_rate_is_stored_when_the_levels_carry_it(db, monkeypatch):
    from stockpilot import levels
    real = levels.for_stock
    monkeypatch.setattr(levels, "for_stock", lambda d: ({**real(d), "target_hit_rate": 0.5, "target_hit_n": 900} if real(d) else None))
    go(db, fake_analyse())
    r = stored(db, "ICICIBANK")
    assert r["target_hit_rate"] == 0.5 and r["target_hit_n"] == 900
