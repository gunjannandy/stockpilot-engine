"""Lane F1: the `reasoning` object (docs/build-lanes-v11.md). Pure builder tests on invented numbers."""
import pytest

from stockpilot import reasoning

CAND = {"symbol": "AAA", "industry": "IT", "composite": 0.7, "flags": [],
        "scores": {"quality": 0.9, "value": 0.98, "momentum": 0.2, "risk": 0.5},
        "metrics": {"close": 150.0, "pe": 8.0, "roe": 0.31, "ret_6m": 0.27, "dist_200dma": -0.04, "vol_1y": 0.3}}
SECTOR = {"pe": 18.0, "n": 12}
CALL = {"symbol": "AAA", "action": "buy", "probability": 0.52, "base_rate": 0.515, "base_rate_n": 3637, "hurdle": 0.02,
        "entry": 149.75, "stop": 135.0, "target": 164.0, "would_buy_if": None, "level_flag": None,
        "change_reason": "It got cheaper.", "summary": "A cheap stock with a fair chance.",
        "reasons": {"moved_by": [{"reason": "Cheap against its sector", "points": 2.0}, {"reason": "Run-up in the price", "points": -1.5}]}}
STOCK = {"range52": {"sentence": "Near the top of its 52-week range."}, "volume": {"sentence": "Trading 3.4 times its usual volume."},
         "results": {"sentence": "Results are due on 05 Dec."}}


def test_code_only_object_has_for_against_and_facts_with_sector_numbers():
    r = reasoning.build("AAA", candidate=CAND, sector=SECTOR, stock=STOCK, as_of="2026-11-23")
    assert r["v"] == 1 and r["stance"] == "none" and "chance" not in r
    assert any("Cheaper than 98% of its sector (PE 8 against 18)" == i["text"] and i["area"] == "value" and i["by"] == "code"
               for i in r["for"])
    assert any(i["area"] == "trend" for i in r["against"])
    assert [f["text"] for f in r["facts"]][:2] == ["Near the top of its 52-week range.", "Trading 3.4 times its usual volume."]
    assert r["headline"]
    for side in ("for", "against"):
        weights = [abs(i["weight"]) for i in r[side]]
        assert weights == sorted(weights, reverse=True) and len(weights) <= 5


def test_a_call_adds_the_chance_levels_and_analyst_items():
    r = reasoning.build("AAA", candidate=CAND, sector=SECTOR, stock=STOCK, call=CALL, as_of="2026-11-23",
                        track={"first_seen": "2026-11-20", "calls_made": 3, "previous_p": 0.49})
    assert r["stance"] == "buy" and r["headline"] == "A cheap stock with a fair chance."
    assert r["chance"]["p"] == 0.52 and r["chance"]["n"] == 3637 and r["chance"]["hurdle_pct"] == 2.0
    assert "52 beat the Nifty" in r["chance"]["explain"] and "+2.0" in r["chance"]["explain"] and "-1.5" in r["chance"]["explain"]
    assert any(i["by"] == "analyst" and i["weight"] == 2.0 for i in r["for"])
    assert any(i["by"] == "analyst" and i["weight"] == -1.5 for i in r["against"])
    assert r["levels"]["entry"] == 149.75 and r["levels"]["stop"] == 135.0
    assert r["track"] == {"first_seen": "2026-11-20", "calls_made": 3, "previous_p": 0.49, "change_reason": "It got cheaper."}
    assert "evidence_note" not in r


def test_thin_base_rate_says_limited_evidence():
    r = reasoning.build("AAA", call={**CALL, "base_rate_n": 12}, as_of="2026-11-23")
    assert r["evidence_note"] == "limited evidence"
    assert reasoning.build("AAA", call={**CALL, "base_rate_n": None}, as_of="2026-11-23")["evidence_note"] == "limited evidence"


def test_change_view_combines_would_buy_if_level_flag_and_code_triggers():
    call = {**CALL, "action": "watch", "would_buy_if": "A close above the 200-day average.", "level_flag": "Results fall before the target date."}
    r = reasoning.build("AAA", candidate=CAND, sector=SECTOR, stock=STOCK, call=call, as_of="2026-11-23")
    texts = [c["text"] for c in r["change_view"]]
    assert "A close above the 200-day average." in texts and "Results fall before the target date." in texts
    line = next(c for c in r["change_view"] if c.get("level") == pytest.approx(156.25, abs=0.01))     # 150 / (1 - 0.04)
    assert line["turns"] == "buy" and "₹156" in line["text"]


def test_hit_rate_and_levels_reasons_pass_through():
    call = {**CALL, "reasons": {**CALL["reasons"], "target_hit_rate": 0.52, "target_hit_n": 1800,
                                "levels_why": "If it falls to ₹135 (just under its recent low of ₹138), sell. Aim for ₹164 (its recent high of ₹164)."}}
    lv = reasoning.build("AAA", call=call, as_of="2026-11-23")["levels"]
    assert lv["target_hit_rate"] == 0.52 and lv["target_hit_n"] == 1800
    assert lv["stop_why"] == "just under its recent low of ₹138" and lv["target_why"] == "its recent high of ₹164"


def test_nothing_to_say_gives_no_object():
    assert reasoning.build("ZZZ", as_of="2026-11-23") is None


def test_analyst_items_keep_only_numbers_found_in_the_brief():
    brief = {"price": {"close": 150.0}, "pe": 8.0, "news": [{"id": "N1", "title": "Order win of 1,200 crore"}]}
    good = {"text": "Won an order worth 1,200 crore", "area": "news", "news_used": ["N1"], "points": 1.5}
    bad = {"text": "Profit will grow 45% next year", "area": "growth"}
    odd_area = {"text": "Trading at PE 8", "area": "astrology"}
    kept, dropped = reasoning.clean_analyst_items([good, bad, odd_area, good, good], brief, side="for")
    assert [i["text"] for i in kept] == [good["text"], odd_area["text"], good["text"]]      # at most three
    assert kept[1]["area"] == "value" or kept[1]["area"] in reasoning.AREAS
    assert kept[0]["by"] == "analyst" and kept[0]["weight"] == 1.5 and kept[0]["news_used"] == ["N1"]
    assert any("45" in d for d in dropped)


def test_every_number_in_a_code_sentence_traces_to_the_inputs():
    r = reasoning.build("AAA", candidate=CAND, sector=SECTOR, stock=STOCK, call=CALL, as_of="2026-11-23")
    pool = reasoning.number_pool(CAND, SECTOR, STOCK, CALL, CALL["reasons"])
    assert reasoning.untraced(r, pool) == []
    r["for"].append({"text": "Profit will jump 77%", "area": "growth", "by": "code", "weight": 1.0})
    assert reasoning.untraced(r, pool) == ["77"]


def test_contract_errors_name_what_is_wrong_for_verify_check_6():
    ok = reasoning.build("AAA", candidate=CAND, sector=SECTOR, stock=STOCK, call=CALL, as_of="2026-11-23")
    assert reasoning.contract_errors(ok) == []
    bad = {**ok, "stance": "maybe", "for": [{"text": "x", "area": "astrology", "by": "me", "weight": 1}] * 6}
    errors = reasoning.contract_errors(bad)
    assert any("stance" in e for e in errors) and any("area" in e for e in errors) and any("more than 5" in e for e in errors)
    assert reasoning.contract_errors({"stance": "buy"}) == ["missing v"]
