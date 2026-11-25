"""Lane V2: verify checks 6, 7 and 10 read the `reasoning` objects on the built site."""
import json

import pytest

from test_data_checks import ctx_for, read, write, site  # noqa: F401  (the site fixture copies the built site per test)
from stockpilot.verify import data, model


def kept_briefs(tmp_path, out):
    """The brief the analyst saw: each stock's analyst lines are written from it, so their numbers sit in it (as the real brief has them)."""
    stocks = []
    for p in sorted((out / "data" / "stock").glob("*.json")):
        r = json.loads(p.read_text()).get("reasoning") or {}
        said = [i["text"] for side in ("for", "against") for i in r.get(side) or [] if i.get("by") == "analyst"]
        if said:
            stocks.append({"symbol": p.stem, "notes": said})
    folder = tmp_path / "briefs"
    folder.mkdir()
    (folder / "2026-11-20.json").write_text(json.dumps({"stocks": stocks, "market": {}}))
    return folder


def first_object(out, name="calls"):
    body = read(out, name)
    card = next(c for k in ("buys", "sells", "follow") for c in body[k] if c.get("reasoning") and c["reasoning"].get("for"))
    return body, card


def stock_with_call(out):
    for p in sorted((out / "data" / "stock").glob("*.json")):
        doc = json.loads(p.read_text())
        if (doc.get("reasoning") or {}).get("chance"):
            return p, doc
    raise AssertionError("no stock with a call in the fixture site")


# ---- 6: every reasoning object is valid ----------------------------------------------------------------------

def test_check6_passes_with_every_reasoning_object_valid(site):
    db, out, day = site
    r = data.check_schema(ctx_for(db, day, out))
    assert r.status == "pass", r.problems[:5]
    assert r.numbers["reasoning_objects"] > 50


def test_check6_catches_a_bad_reasoning_object_on_a_call_card(site):
    db, out, day = site
    body, card = first_object(out)
    card["reasoning"]["for"][0]["area"] = "astrology"
    card["reasoning"]["stance"] = "maybe"
    write(out, "calls", body)
    r = data.check_schema(ctx_for(db, day, out))
    text = " ".join(r.problems)
    assert r.status == "fail" and card["symbol"] in text and "astrology" in text and "maybe" in text


def test_check6_catches_a_bad_reasoning_object_in_a_stock_file(site):
    db, out, day = site
    p, doc = stock_with_call(out)
    doc["reasoning"]["against"] = [{"text": "x", "area": "value", "by": "code"}] * 6
    p.write_text(json.dumps(doc))
    r = data.check_schema(ctx_for(db, day, out))
    assert r.status == "fail" and "more than 5 items" in " ".join(r.problems)


# ---- 7: a base rate on too few cases says "limited evidence" -------------------------------------------------

def test_check7_site_part_catches_a_base_rate_on_zero_cases_without_the_note(site):
    db, out, day = site
    p, doc = stock_with_call(out)
    doc["reasoning"]["chance"]["n"] = 0
    doc["reasoning"].pop("evidence_note", None)
    p.write_text(json.dumps(doc))
    r = model.check_site_evidence(ctx_for(db, day, out))
    assert r.problems and doc["symbol"] in r.problems[0] and "0 cases" in r.problems[0] and "limited evidence" in r.problems[0]


def test_check7_site_part_accepts_the_note_and_the_clean_site(site):
    db, out, day = site
    assert model.check_site_evidence(ctx_for(db, day, out)).problems == []
    p, doc = stock_with_call(out)
    doc["reasoning"]["chance"]["n"] = 0
    doc["reasoning"]["evidence_note"] = "limited evidence"
    p.write_text(json.dumps(doc))
    assert model.check_site_evidence(ctx_for(db, day, out)).problems == []


def test_check7_is_wired_to_the_site_part(site):
    db, out, day = site
    p, doc = stock_with_call(out)
    doc["reasoning"]["chance"]["n"] = 0
    doc["reasoning"].pop("evidence_note", None)
    p.write_text(json.dumps(doc))
    assert any("0 cases" in x for x in model.check_bounds(ctx_for(db, day, out)).problems)


# ---- 10: every number in an analyst sentence traces ----------------------------------------------------------

def test_check10_site_part_passes_on_the_clean_site(site, tmp_path):
    db, out, day = site
    r = model.check_site_numbers(ctx_for(db, day, out, briefs=kept_briefs(tmp_path, out)))
    assert r.problems == [], r.problems[:5]
    assert r.numbers["analyst_sentences"] > 0


def test_check10_site_part_catches_an_invented_number_in_an_analyst_line(site, tmp_path):
    db, out, day = site
    briefs = kept_briefs(tmp_path, out)
    p, doc = stock_with_call(out)
    doc["reasoning"]["for"].insert(0, {"text": "Brokers raised targets by 4,812 rupees", "area": "news", "by": "analyst", "weight": 1.0})
    p.write_text(json.dumps(doc))
    r = model.check_site_numbers(ctx_for(db, day, out, briefs=briefs))
    assert doc["symbol"] in " ".join(r.problems) and "4812" in " ".join(r.problems)


def test_check10_site_part_catches_an_invented_number_in_the_headline_and_chance_explanation(site, tmp_path):
    db, out, day = site
    briefs = kept_briefs(tmp_path, out)
    p, doc = stock_with_call(out)
    doc["reasoning"]["headline"] = "Up 7351% soon."
    doc["reasoning"]["chance"]["explain"] = "Out of 100 stocks, 6173 won."
    p.write_text(json.dumps(doc))
    text = " ".join(model.check_site_numbers(ctx_for(db, day, out, briefs=briefs)).problems)
    assert "7351" in text and "6173" in text


def test_check10_is_wired_to_the_site_part(site, tmp_path):
    db, out, day = site
    briefs = kept_briefs(tmp_path, out)
    p, doc = stock_with_call(out)
    doc["reasoning"]["for"].insert(0, {"text": "Brokers raised targets by 4,812 rupees", "area": "news", "by": "analyst", "weight": 1.0})
    p.write_text(json.dumps(doc))
    r = model.check_analyst_numbers(ctx_for(db, day, out, briefs=briefs))
    assert "4812" in " ".join(r.problems)


# ---- the pool: where a red test showed a false pass ----------------------------------------------------------

def test_a_price_does_not_license_the_same_digits_as_a_percent():
    from stockpilot import reasoning
    pool = reasoning.number_pool({"close": 48.12, "pe": 7.8, "score": 0.68})
    assert "4812" not in pool and "780" not in pool          # a rupee price or a ratio is not a fraction: it has no percent form
    assert "68" in pool and "32" in pool and "48.12" in pool   # a fraction still reads as a percent


# ---- C10: "52" in a stock's analyst line (issue #14) ---------------------------------------------------------

def _say(out, text):
    p, doc = stock_with_call(out)
    doc["reasoning"]["for"].insert(0, {"text": text, "area": "trend", "by": "analyst", "weight": 1.0})
    p.write_text(json.dumps(doc))
    return doc


@pytest.mark.parametrize("text", ["Trading near its 52-week high", "At the top of its 52 weeks range", "Close to the 52-wk low",
                                  "Near the 52‑week high", "Up from its 12-month low"])
def test_check10_a_period_label_is_not_a_figure(site, tmp_path, text):
    db, out, day = site
    briefs = kept_briefs(tmp_path, out)
    doc = _say(out, text)
    r = model.check_site_numbers(ctx_for(db, day, out, briefs=briefs))
    assert not any(doc["symbol"] in p for p in r.problems), r.problems


@pytest.mark.parametrize("text", ["Down 52% in a year", "Target of 52 rupees", "52 analysts raised targets", "Ranked 52 of 400 in its sector",
                                  "Up 52 days in a row", "Its 52-week high of 5,234 is far off"])
def test_a_real_figure_52_is_still_untraced_when_in_neither_data_nor_brief(text):
    from stockpilot import reasoning
    bad = reasoning.untraced({"for": [{"text": text}]}, reasoning.number_pool({"close": 100.5}))
    assert "52" in bad or "5234" in bad, (text, bad)


@pytest.mark.parametrize("text", ["Trading near its 52-week high", "At the top of its 52 weeks range", "Close to the 52-wk low",
                                  "Near the 52\u2011week high", "Up from its 12-month low", "A 52 week high"])
def test_a_period_label_is_not_a_figure_even_when_the_data_lacks_52(text):
    from stockpilot import reasoning
    assert reasoning.untraced({"for": [{"text": text}]}, reasoning.number_pool({"close": 100.5})) == []


def test_check10_no_brief_kept_still_passes_a_number_that_is_in_the_stocks_own_data(site, tmp_path):
    db, out, day = site
    p, doc = stock_with_call(out)
    close = doc["reasoning"]["levels"]["entry"] if doc["reasoning"].get("levels") else None
    assert close is not None
    doc["reasoning"]["for"].insert(0, {"text": f"Entry near {close:g}", "area": "trend", "by": "analyst", "weight": 1.0})
    p.write_text(json.dumps(doc))
    empty = tmp_path / "nobriefs"
    empty.mkdir()
    r = model.check_site_numbers(ctx_for(db, day, out, briefs=empty))
    assert not any(doc["symbol"] in x for x in r.problems), r.problems
    r2 = model.check_site_numbers(ctx_for(db, day, out, briefs=tmp_path / "missing"))
    assert not any(doc["symbol"] in x for x in r2.problems), r2.problems


def test_check10_no_brief_kept_still_fails_a_number_in_neither(site, tmp_path):
    db, out, day = site
    p, doc = stock_with_call(out)
    doc["reasoning"]["for"].insert(0, {"text": "Brokers see 4,812 as fair", "area": "news", "by": "analyst", "weight": 1.0})
    p.write_text(json.dumps(doc))
    r = model.check_site_numbers(ctx_for(db, day, out, briefs=tmp_path / "missing"))
    assert "4812" in " ".join(r.problems)


def test_check10_reads_the_brief_that_holds_the_stock_not_just_the_newest_file(site, tmp_path):
    db, out, day = site
    p, doc = stock_with_call(out)
    doc["reasoning"]["for"].insert(0, {"text": "Brokers see 4,812 as fair", "area": "news", "by": "analyst", "weight": 1.0})
    p.write_text(json.dumps(doc))
    folder = tmp_path / "briefs"
    folder.mkdir()
    (folder / "2026-11-20.json").write_text(json.dumps({"stocks": [{"symbol": doc["symbol"], "notes": ["target 4,812"]}], "market": {}}))
    (folder / "2026-11-21.json").write_text(json.dumps({"stocks": [{"symbol": "OTHER"}], "market": {}}))    # newest, but not this stock
    r = model.check_site_numbers(ctx_for(db, day, out, briefs=folder))
    assert not any(doc["symbol"] in x for x in r.problems), r.problems
