"""Lane F1: the `reasoning` object rides on every stock the site shows (docs/build-lanes-v11.md, "The contract")."""
import json

from conftest import load
from stockpilot import reasoning

AREAS = set(reasoning.AREAS)


def lines(r):
    return len(r.get("for", [])) + len(r.get("against", [])) + len(r.get("facts", []))


def check(r, where):
    assert r and r["v"] == 1, where
    assert r["stance"] in ("buy", "hold", "watch", "weak", "sell", "none"), where
    assert r["headline"], where
    for side in ("for", "against"):
        items = r.get(side, [])
        assert len(items) <= 5, where
        assert all(i["area"] in AREAS and i["by"] in ("analyst", "code") and i["text"] for i in items), where
        weights = [abs(i["weight"] or 0) for i in items]
        assert weights == sorted(weights, reverse=True), where
    assert all(f["area"] in AREAS for f in r.get("facts", [])), where


def test_every_watchlist_row_has_an_object_with_at_least_two_lines(built):
    rows = load(built, "watchlist")["rows"]
    assert rows
    for row in rows:
        check(row.get("reasoning"), row["symbol"])
        if row["symbol"] != "ASMCO":        # the one stock the screen excludes: it still has facts or a flag, never nothing
            assert lines(row["reasoning"]) >= 2, row["symbol"]


def test_every_ideas_row_has_an_object_and_a_near_miss_has_its_trigger(built):
    ideas = load(built, "ideas")
    assert ideas["ranking"] and ideas["near_misses"]
    for row in ideas["ranking"] + ideas["near_misses"]:
        check(row["reasoning"], row["symbol"])
        assert lines(row["reasoning"]) >= 2, row["symbol"]
    for row in ideas["near_misses"]:
        assert row["trigger"] in [c["text"] for c in row["reasoning"]["change_view"]]


def test_every_call_card_has_an_object_in_today_and_calls(built):
    today, calls = load(built, "today"), load(built, "calls")
    cards = [c for k in ("buy", "sell", "watch_triggers", "keep", "not_yet") for c in today[k]]
    cards += [c for k in ("buys", "sells", "follow") for c in calls[k]]
    assert len(cards) > 10
    for c in cards:
        check(c["reasoning"], c["symbol"])
        assert c["reasoning"]["chance"]["p"] == c["probability"], c["symbol"]


def test_stock_files_carry_the_full_object_and_a_stock_without_a_call_gets_code_only(built):
    called = json.loads((built / "data/stock/ICICIBANK.json").read_text())["reasoning"]
    check(called, "ICICIBANK")
    assert called["stance"] == "buy" and called["chance"]["n"] == 3637 and "evidence_note" not in called
    assert called["levels"]["target_hit_rate"] == 0.52 and called["levels"]["stop_why"] == "just under its recent low of ₹95"
    assert any(i["by"] == "analyst" and i["text"] == "Profit grew 12% in the last quarter" for i in called["for"])
    assert called["track"]["first_seen"] <= "2026-11-19" and called["track"]["calls_made"] >= 2 and called["track"]["previous_p"] == 0.6
    assert called["track"]["change_reason"] == "Its chance rose from 60% to 68%."
    assert {"text": "A close above its 50-day average.", "turns": "buy"} in called["change_view"]
    thin = json.loads((built / "data/stock/WIPRO.json").read_text())["reasoning"]
    assert thin["evidence_note"] == "limited evidence"
    objs = [json.loads(p.read_text()).get("reasoning") for p in sorted((built / "data/stock").glob("*.json"))]
    code_only = [r for r in objs if r and r["stance"] == "none"]
    assert code_only and all("chance" not in r and "levels" not in r for r in code_only)      # no call: code lines and facts only
    assert all(lines(r) >= 1 for r in code_only)


def test_numbers_in_every_sentence_trace_to_the_data(built):
    """The spot check verify's check 10 will run: every number written in a sentence is in the stock's own data."""
    bad = []
    for path in sorted((built / "data/stock").glob("*.json"))[:60]:
        doc = json.loads(path.read_text())
        r = doc.get("reasoning")
        if not r:
            continue
        pool = reasoning.number_pool({k: v for k, v in doc.items() if k != "reasoning"}, r.get("levels"), r.get("chance"), r.get("track"))
        # the screen's metrics are not in the stock file; its percentile lines carry them, so those lines are checked by test_reasoning
        skip = ("for", "against", "change_view") + (("headline",) if r["stance"] == "none" else ())        # code-only headlines quote the percentile lines
        found = [(doc["symbol"], n) for n in reasoning.untraced({k: v for k, v in r.items() if k not in skip}, pool)]
        bad += found
    assert bad == []


def test_every_object_in_the_site_passes_the_contract_check(built):
    seen = 0
    docs = [load(built, n) for n in ("today", "calls", "watchlist", "ideas", "portfolio")]
    docs += [json.loads(p.read_text()) for p in (built / "data/stock").glob("*.json")]

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("reasoning"), dict):
                yield x["reasoning"]
            for v in x.values():
                yield from walk(v)
        elif isinstance(x, list):
            for v in x:
                yield from walk(v)
    for doc in docs:
        for r in walk(doc):
            seen += 1
            assert reasoning.contract_errors(r) == [], r
    assert seen > 50


def test_holdings_carry_the_object(built):
    held = [h for h in load(built, "portfolio")["holdings"] if h.get("symbol")]
    assert held and any(h.get("reasoning") for h in held if h["kind"] == "equity")
