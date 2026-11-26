"""T17: the model's strict forecast form and the twelve code checks. A fake model stands in; nothing touches a network."""
import copy

from stockpilot.calls.decide import Rules
from stockpilot import forecast_form as ff

RULES = Rules()


def brief(base3=0.50, base6=0.52, news=None):
    return {"symbol": "FIXA", "as_of": "2026-11-25", "price": 100.0,
            "base": {"chance_3m": base3, "chance_6m": base6,
                     "low_1m": 96.0, "likely_1m": 101.0, "high_1m": 106.0,
                     "low_3m": 90.0, "likely_3m": 104.0, "high_3m": 118.0,
                     "low_6m": 85.0, "likely_6m": 108.0, "high_6m": 130.0},
            "facts": {"f1": {"date": "2026-11-20", "profit_growth_pct": 18, "pe": 22}},
            "news": news if news is not None else [
                {"id": "n1", "date": "2026-11-24", "sources": 1, "filing": False, "impact": "medium"}]}


def sent(en, bn="বাক্য।"):
    return {"text": en, "text_bn": bn}


def good(**over):
    f = {"call": "wait", "confidence": "medium",
         "chance": {"m3": 52, "m6": 55},
         "range": {"m1": {"low": 96, "likely": 101, "high": 106}, "m3": {"low": 90, "likely": 104, "high": 118},
                   "m6": {"low": 85, "likely": 108, "high": 130}},
         "company_history": {"verdict": "steady", "line": "Profit grew 18 percent.", "line_bn": "লাভ ১৮ শতাংশ বেড়েছে।", "facts_used": ["f1"]},
         "market_weight": {"verdict": "middle", "line": "Mid-sized.", "line_bn": "মাঝারি।", "facts_used": ["f1"]},
         "news": [{"id": "n1", "what_happened": "New order.", "what_happened_bn": "নতুন অর্ডার।", "effect": "up",
                   "horizon": "m3", "already_in_price": "no"}],
         "reasons_for": [{"area": "news", "text": "New order.", "text_bn": "নতুন অর্ডার।", "evidence_ids": ["n1"], "points": 2, "horizon": "m3"}],
         "reasons_against": [{"area": "risk", "text": "Price is full.", "text_bn": "দাম চড়া।", "evidence_ids": ["f1"], "points": 1, "horizon": "m3"}],
         "adjustments": [{"area": "news", "from_evidence": "n1", "points": 2, "horizon": "m3"},
                         {"area": "news", "from_evidence": "n1", "points": 3, "horizon": "m6"}],
         "would_change_view": [sent("A fall below 90.", "৯০-এর নিচে নামলে।")],
         "risks": [sent("Market falls.", "বাজার পড়লে।")],
         "summary": "Order win, but not enough yet.", "summary_bn": "অর্ডার পেয়েছে, তবে যথেষ্ট নয়।",
         "broken_reason": None}
    f.update(over)
    return f


def fake(form, model="fake-1", skeptic=None, seen=None):
    def analyse(b, role, **kw):
        if seen is not None:
            seen.append(role)
        if role == "second_opinion":
            return {"model": "fake-skeptic", "net": skeptic}
        return {"model": model, "form": copy.deepcopy(form(b) if callable(form) else form)}
    return analyse


def run(form, b=None, **kw):
    return ff.forecast_stock(b or brief(), fake(form, **kw), RULES)


# --- acceptance 1: a number that does not match the data
def test_number_not_in_data_is_rejected():
    r = run(good(summary="Profit jumped 91 percent.", summary_bn="লাভ 91 শতাংশ বেড়েছে।"))
    assert r["status"] == "rejected"
    assert any("91" in e for e in r["errors"])
    assert r["call"] == "wait" and r["chance_3m"] == 0.50       # falls back to the code's own start
    assert r["model"] == "fake-1"                               # still records which model wrote it


def test_number_in_data_is_accepted():
    r = run(good(summary="Profit grew 18 percent.", summary_bn="লাভ 18 শতাংশ বেড়েছে।"))
    assert r["status"] == "ok", r["errors"]


def test_bengali_must_keep_the_numbers():
    r = run(good(summary="Profit grew 18 percent.", summary_bn="লাভ বেড়েছে।"))
    assert r["status"] == "rejected" and any("Bengali" in e for e in r["errors"])


def test_every_sentence_needs_bengali():
    f = good()
    f["risks"] = [{"text": "Market falls.", "text_bn": ""}]
    assert run(f)["status"] == "rejected"


# --- acceptance 2: adjustment limits
def test_item_over_five_points_is_rejected():
    f = good(chance={"m3": 58, "m6": 55})
    f["adjustments"][0]["points"] = 8
    r = run(f)
    assert r["status"] == "rejected" and any("5 points" in e for e in r["errors"])


def test_total_over_limit_is_rejected():
    f = good(chance={"m3": 65, "m6": 55})
    f["adjustments"] = [{"area": a, "from_evidence": "f1", "points": 5, "horizon": "m3"} for a in ("results", "owners", "sector")]
    f["reasons_for"][0]["evidence_ids"] = ["f1"]
    r = run(f)
    assert r["status"] == "rejected" and any("total" in e for e in r["errors"])


def test_chance_must_equal_base_plus_adjustments():
    r = run(good(chance={"m3": 60, "m6": 55}))
    assert r["status"] == "rejected" and any("add up" in e for e in r["errors"])


def test_adjustment_in_a_mechanical_area_is_rejected():
    f = good()
    f["adjustments"][0]["area"] = "trend"
    assert run(f)["status"] == "rejected"


def test_already_in_price_news_moves_nothing():
    f = good()
    f["news"][0]["already_in_price"] = "yes"
    assert run(f)["status"] == "rejected"


def confirmed_news():
    return [{"id": "n1", "date": "2026-11-25", "sources": 1, "filing": True, "impact": "high"}]


def big_news_form(points=14):
    f = good(chance={"m3": 50 + points, "m6": 55}, call="buy")
    f["adjustments"] = [{"area": "news", "from_evidence": "n1", "points": points, "horizon": "m3"},
                        {"area": "news", "from_evidence": "n1", "points": 3, "horizon": "m6"}]
    return f


def test_confirmed_news_buy_may_pass_the_limits_and_is_labelled():
    r = run(big_news_form(), brief(base3=0.50, news=confirmed_news()))
    assert r["status"] == "ok", r["errors"]
    assert r["call"] == "buy" and r["news_buy"] is True and r["route"] == "news"
    assert r["chance_3m"] == 0.64


def test_two_sources_also_confirm():
    n = [{"id": "n1", "date": "2026-11-25", "sources": 2, "filing": False, "impact": "high"}]
    r = run(big_news_form(), brief(news=n))
    assert r["status"] == "ok" and r["news_buy"] is True


def test_one_source_no_filing_does_not_confirm():
    n = [{"id": "n1", "date": "2026-11-25", "sources": 1, "filing": False, "impact": "high"}]
    r = run(big_news_form(), brief(news=n))
    assert r["status"] == "rejected"


def test_medium_impact_never_confirms():
    n = [{"id": "n1", "date": "2026-11-25", "sources": 3, "filing": True, "impact": "medium"}]
    assert run(big_news_form(), brief(news=n))["status"] == "rejected"


# --- acceptance 3: below the floor, code never makes a buy
def test_below_floor_without_confirmed_event_is_never_a_buy():
    f = good(chance={"m3": 62, "m6": 55}, call="buy")        # model says buy, within the caps: 50 + 5 + 5 ... two items
    f["adjustments"] = [{"area": "news", "from_evidence": "n1", "points": 5, "horizon": "m3"},
                        {"area": "results", "from_evidence": "f1", "points": 5, "horizon": "m3"},
                        {"area": "news", "from_evidence": "n1", "points": 2, "horizon": "m3"},
                        {"area": "news", "from_evidence": "n1", "points": 3, "horizon": "m6"}]
    r = run(f, brief(base3=0.50))
    assert r["status"] == "ok", r["errors"]
    assert r["call"] != "buy" and r["news_buy"] is False
    assert r["chance_3m"] < RULES.buy_at


def test_start_above_floor_may_buy_without_news():
    f = good(chance={"m3": 59, "m6": 55}, call="buy")
    f["adjustments"] = [{"area": "results", "from_evidence": "f1", "points": 2, "horizon": "m3"},
                        {"area": "results", "from_evidence": "f1", "points": 3, "horizon": "m6"}]
    r = run(f, brief(base3=0.57))
    assert r["call"] == "buy" and r["news_buy"] is False and r["route"] == "code"


def test_model_cannot_force_buy_below_line_by_saying_so():
    r = run(good(call="buy"))
    assert r["call"] == "wait"


# --- the other code checks
def test_range_must_be_ordered():
    f = good()
    f["range"]["m3"] = {"low": 120, "likely": 104, "high": 118}
    assert run(f)["status"] == "rejected"


def test_range_far_from_code_range_is_rejected():
    f = good()
    f["range"]["m3"] = {"low": 40, "likely": 104, "high": 260}
    assert run(f)["status"] == "rejected"


def test_unknown_evidence_id_is_rejected():
    f = good()
    f["reasons_for"][0]["evidence_ids"] = ["zz"]
    assert run(f)["status"] == "rejected"


def test_evidence_dated_after_today_is_rejected():
    n = [{"id": "n1", "date": "2026-11-30", "sources": 1, "filing": False, "impact": "medium"}]
    assert run(good(), brief(news=n))["status"] == "rejected"


def test_date_after_today_in_text_is_rejected():
    r = run(good(summary="Results due 2026-12-10.", summary_bn="ফল 2026-12-10।"))
    assert r["status"] == "rejected"


def test_extra_key_and_bad_enum_are_rejected():
    assert run(good(extra=1))["status"] == "rejected"
    assert run(good(confidence="sure"))["status"] == "rejected"


def test_too_many_reasons_rejected():
    f = good()
    f["reasons_for"] = f["reasons_for"] * 4
    assert run(f)["status"] == "rejected"


def test_six_month_chance_within_fifteen_of_three_month():
    f = good(chance={"m3": 52, "m6": 70})
    f["adjustments"][1]["points"] = 5
    assert run(f)["status"] == "rejected"


def test_retry_once_then_fall_back(monkeypatch=None):
    seen = []
    r = ff.forecast_stock(brief(), fake(good(confidence="sure"), seen=seen), RULES)
    assert seen.count("forecast") == 2 and r["status"] == "rejected"


def test_second_try_can_succeed():
    calls = []

    def analyse(b, role, **kw):
        calls.append(kw.get("errors"))
        form = good(confidence="sure") if len(calls) == 1 else good()
        return {"model": "fake-1", "form": form}
    r = ff.forecast_stock(brief(), analyse, RULES)
    assert r["status"] == "ok" and calls[0] is None and calls[1]


def test_record_keeps_raw_output_and_base():
    r = run(good())
    assert r["raw"]["summary"] and r["base"]["chance_3m"] == 0.50 and r["model"] == "fake-1"


def test_unknown_model_name_is_a_failure():
    r = ff.forecast_stock(brief(), lambda b, role, **kw: {"model": "", "form": good()}, RULES)
    assert r["status"] == "rejected"


# --- second opinion
def test_second_opinion_only_within_five_points_of_a_line():
    seen = []
    run(good(chance={"m3": 50, "m6": 55}), brief(base3=0.48), skeptic={"m3": 0, "m6": 0}, seen=seen)   # 50: 7 from 57, 10 from 40
    assert "second_opinion" not in seen
    seen = []
    f = good(chance={"m3": 55, "m6": 55})
    f["adjustments"][0]["points"] = 5
    ff.forecast_stock(brief(base3=0.50), fake(f, skeptic={"m3": 1, "m6": 3}, seen=seen), RULES)
    assert "second_opinion" in seen


def test_second_opinion_can_only_shrink():
    f = good(chance={"m3": 55, "m6": 55})
    f["adjustments"][0]["points"] = 5
    r = ff.forecast_stock(brief(base3=0.50), fake(f, skeptic={"m3": 9, "m6": 3}), RULES)
    assert r["chance_3m"] == 0.55                       # asked to grow: ignored
    r = ff.forecast_stock(brief(base3=0.50), fake(f, skeptic={"m3": 2, "m6": 3}), RULES)
    assert r["chance_3m"] == 0.52 and r["second_opinion_model"] == "fake-skeptic"
    r = ff.forecast_stock(brief(base3=0.50), fake(f, skeptic={"m3": -4, "m6": 3}), RULES)
    assert r["chance_3m"] == 0.50                       # opposite sign shrinks to zero, never flips


def test_second_opinion_can_pull_a_marginal_buy_back():
    f = good(chance={"m3": 58, "m6": 55}, call="buy")
    f["adjustments"] = [{"area": "results", "from_evidence": "f1", "points": 1, "horizon": "m3"},
                        {"area": "results", "from_evidence": "f1", "points": 3, "horizon": "m6"}]
    r = ff.forecast_stock(brief(base3=0.57), fake(f, skeptic={"m3": 0, "m6": 0}), RULES)
    assert r["chance_3m"] == 0.57 and r["call"] == "buy"
    f["chance"]["m3"] = 57
    f["adjustments"][0]["points"] = 0
    r = ff.forecast_stock(brief(base3=0.57), fake(f, skeptic={"m3": 0, "m6": 0}), RULES)
    assert r["call"] == "buy"
