import json

import pytest

from seed_site import AS_OF, TOKENS, seed
from stockpilot import site


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("site")
    db = seed(root / "sp.duckdb")
    out = root / "site"
    site.build(db, out, today=AS_OF, budget_inr=100000, now=__import__("datetime").datetime(2026, 11, 20, 19, 30), tokens=TOKENS)
    return out


def data(built, name):
    return json.loads((built / "data" / f"{name}.json").read_text())


def test_site_has_pages_and_one_json_per_tab(built):
    for f in ["index.html", "app.css", "app.js"]:
        assert (built / f).exists()
    for tab in ["meta", "today", "market", "ideas", "watchlist", "portfolio", "record", "health", "lookup", "search"]:
        assert (built / "data" / f"{tab}.json").exists(), tab


def test_today_groups_actions_and_tax_timing(built):
    t = data(built, "today")
    assert [a["symbol"] for a in t["buy"]] == ["ICICIBANK", "M&M", "SUNPHARMA"]
    assert [a["symbol"] for a in t["sell"]] == ["WIPRO"]
    wipro = next(a for a in t["sell"] if a["symbol"] == "WIPRO")
    assert "long-term" in wipro["tax_note"] and wipro["quantity"] == 300
    mm = t["buy"][1]
    assert mm["skeptic"]["summary"].startswith("Valuation") and mm["moved_by"][0]["points"] == 6
    assert t["budget"] == {"month": "2026-11", "total": 100000, "planned": 90000, "left": 10000}
    assert "steady" in t["market_mood"].lower() and not t["nothing_to_do"]


def test_nothing_to_do_is_a_valid_call(tmp_path):
    db = seed(tmp_path / "sp.duckdb")
    db.execute("update calls set action = 'watch' where made_on = ?", [AS_OF])
    site.build(db, tmp_path / "s", today=AS_OF, budget_inr=100000)
    t = json.loads((tmp_path / "s" / "data" / "today.json").read_text())
    assert t["nothing_to_do"] and t["buy"] == [] and t["sell"] == []


def test_history_file_for_each_action_has_averages(built):
    h = json.loads((built / "data" / "history" / "ICICIBANK.json").read_text())
    assert len(h["close"]) == len(h["dma200"]) == len(h["dates"]) == 250
    assert h["dma200"][-1] is not None


def test_market_ideas_and_exclusions(built):
    m = data(built, "market")
    assert 0 <= m["breadth"] <= 1 and {s["industry"] for s in m["sectors"]} >= {"IT", "Banks"}
    assert m["valuation"]["pe_now"] and 0 <= m["valuation"]["percentile"] <= 100
    assert m["events"][0]["text"].startswith("Guru Nanak")
    i = data(built, "ideas")
    assert "ASMCO" not in [r["symbol"] for r in i["ranking"]]
    assert i["ranking"][0]["rank"] == 1 and i["near_misses"] and i["near_misses"][0]["trigger"]
    assert any(e["symbol"] == "ASMCO" for e in i["excluded"])


def test_watchlist_sorted_by_need_attention(built):
    w = data(built, "watchlist")
    assert w["rows"][0]["symbol"] == "SBIN"          # volume spike plus a dividend
    assert 120 <= len(w["rows"]) <= 135
    sbin = w["rows"][0]
    assert sbin["volume_spike"] >= 3 and "Dividend" in sbin["actions"][0]
    assert any(r["symbol"] == "WIPRO" and r["results_date_note"] for r in w["rows"])
    assert all("dist_50dma" in r and "dist_200dma" in r for r in w["rows"])


def test_portfolio_holdings_lots_and_extras(built):
    p = data(built, "portfolio")
    infy = next(h for h in p["holdings"] if h["symbol"] == "INFY")
    assert infy["verdict"] == "hold" and len(infy["lots"]) == 2 and infy["lots"][0]["days_held"] > 300
    assert p["allocation"]["current"]["equity_funds"] > 0 and p["allocation"]["labels"]["stocks"] == "Indian stocks"
    assert p["allocation"]["proposed"]["stocks"] == 0.55
    assert p["tax"]["harvest_room"] == 42000 and p["funds"] and p["opportunities"]


def test_record_scores_calls_by_horizon(built):
    r = data(built, "record")
    s = r["summary"]["3m"]
    assert s["n"] > 20 and 0 <= s["hit_rate"] <= 1 and 0 <= s["brier"] <= 1
    assert r["calibration"]["3m"] and r["dates"][0] == "2026-11-20"
    assert len(r["calls"]) == 75


def test_health_freshness_tokens_and_queue(built):
    h = data(built, "health")
    assert any(q["status"] == "pending" for q in h["queue"])
    assert next(t for t in h["tokens"] if t["name"] == "Kite")["days_left"] == 3
    assert {f["name"] for f in h["freshness"]} >= {"Prices", "Holdings"}
    meta = data(built, "meta")
    assert meta["as_of"] == "2026-11-20" and meta["holdings"]["stale"] is False


def test_lookup_fact_sheet_has_peers_and_valuation(built):
    lk = data(built, "lookup")
    s = lk["INFY"]
    assert s["name"] == "Infosys" and s["verdict"]["action"] == "hold"
    assert "INFY" not in {p["symbol"] for p in s["peers"]} and 1 <= len(s["peers"]) <= 5 and s["pe_range"]["peers"] >= 2
    assert any(x["symbol"] == "TCS" for x in data(built, "search"))


def test_no_secrets_or_model_text_in_site(built):
    text = "".join(p.read_text() for p in built.rglob("*.json"))
    assert "CLAUDE_CODE_OAUTH_TOKEN" not in text


# ---- lane U: the page says one thing, once ----

def _build(tmp_path, edit=None):
    db = seed(tmp_path / "sp.duckdb")
    if edit:
        edit(db)
    out = tmp_path / "s"
    site.build(db, out, today=AS_OF, budget_inr=100000, now=__import__("datetime").datetime(2026, 11, 20, 19, 30), tokens=TOKENS)
    return lambda name: json.loads((out / "data" / f"{name}.json").read_text())


def test_one_row_per_company_in_the_watchlist(built):
    symbols = [r["symbol"] for r in data(built, "watchlist")["rows"]]     # TCS and ITC are also on BSE
    assert len(symbols) == len(set(symbols))
    assert "TCS" in symbols and "ITC" in symbols


def test_a_split_holding_is_one_row_with_the_total(built):
    hs = [h for h in data(built, "portfolio")["holdings"] if h["symbol"] == "HDFCBANK"]
    assert len(hs) == 1 and hs[0]["quantity"] == 737
    assert len({h["symbol"] for h in data(built, "portfolio")["holdings"]}) == len(data(built, "portfolio")["holdings"])


def test_a_rerun_does_not_double_the_calls(tmp_path):
    def rerun(db):   # the Re-run button writes the same day's calls again
        db.execute("insert into calls (made_on, symbol, kind, action, probability, base_rate, horizon_days, entry, stop, target, "
                   "size_inr, reasons, risks, news, runner, unproven) select made_on, symbol, kind, action, probability - 0.01, "
                   "base_rate, horizon_days, entry, stop, target, size_inr, reasons, risks, news, runner, unproven "
                   "from calls where made_on = ?", [AS_OF])
    d = _build(tmp_path, rerun)
    t = d("today")
    every = [c["symbol"] for k in ("buy", "sell", "watch_triggers", "keep", "not_yet") for c in t[k]]
    assert len(every) == len(set(every)) == 30
    assert [c["symbol"] for c in t["buy"]] == ["ICICIBANK", "M&M", "SUNPHARMA"]
    assert sum(1 for c in d("record")["calls"] if c["made_on"] == str(AS_OF)) == 30


def test_funds_and_rsus_are_priced_not_shown_at_cost(built):
    hs = {h["symbol"]: h for h in data(built, "portfolio")["holdings"]}
    ppfas = hs["INF879O01027"]                       # a fund's symbol is its ISIN, as Kite reports it
    assert ppfas["name"] == "Parag Parikh Flexi Cap Fund"
    assert ppfas["price"] == 80.5 and round(ppfas["gain_pct"], 3) == round(80.5 / 68 - 1, 3)
    assert hs["NOW"]["value"] > 12 * 640 * 83 and hs["NOW"]["gain_pct"] > 0
    assert len(hs) == 20


def test_today_opens_with_one_plain_sentence(built, tmp_path):
    assert data(built, "today")["headline"] == "Buy 3 stocks and sell 1 today."
    d = _build(tmp_path, lambda db: db.execute("update calls set action = 'watch' where made_on = ?", [AS_OF]))
    assert d("today")["headline"] == "Nothing to do today."
    (tmp_path / "one").mkdir()
    one = _build(tmp_path / "one", lambda db: db.execute(
        "update calls set action = 'watch' where made_on = ? and symbol <> 'ICICIBANK' and action in ('buy', 'sell')", [AS_OF]))
    assert one("today")["headline"] == "Buy 1 stock today."


def test_watch_triggers_only_hold_stocks_with_a_reason_today(built):
    t = data(built, "today")
    trig = {c["symbol"] for c in t["watch_triggers"]}
    assert "SBIN" in trig and "AXISBANK" in trig            # volume spike and dividend; bonus issue
    assert "TCS" not in trig                                 # a Watch call with nothing happening goes to Not yet
    assert {"TCS", "HCLTECH"} <= {c["symbol"] for c in t["not_yet"]}
    assert len(trig) < 8
    assert all(c["why_today"] for c in t["watch_triggers"])


def test_each_holding_says_when_it_turns_long_term(built):
    hs = {h["symbol"]: h for h in data(built, "portfolio")["holdings"]}
    assert hs["WIPRO"]["tax_note"] == "100 turn long-term on 2 Dec 2026"
    assert hs["LT"]["tax_note"] == "All long-term"
    assert hs["NOW"]["tax_note"] is None


def test_market_says_expensive_or_cheap_in_words(built):
    m = data(built, "market")
    v = m["valuation"]
    assert v["verdict"] in ("Expensive against its own history.", "Cheap against its own history.", "About normal against its own history.")
    assert m["headline"].startswith("The market looks")


def test_record_and_health_lead_with_a_verdict(built):
    r = data(built, "record")
    assert r["headline"].startswith("Over 3 months we beat the Nifty after costs and tax 58% of the time, from 45 calls.")
    assert r["model_added_value"] in (True, False) and r["summary"]["3m"]["n"] == 45
    h = data(built, "health")
    assert h["headline"] == "3 things need you."          # R17: the seeded funds have under 3 years of NAVs; C: plus the seeded open problem
    assert h["needs"][0] == "Kite expires in 3 days." and len(h["needs"]) == 2
    assert h["needs"][1].startswith("Fund NAV history reaches back only ")
    assert data(built, "meta")["status"] == {"ok": True, "text": "Everything is up to date."}
    assert data(built, "portfolio")["headline"].startswith("Worth about")


def test_account_pages_are_new_files_and_empty_without_trades(built):
    assert data(built, "smallcase")["months"] == [] and data(built, "own_record")["closed"] == 0
    assert data(built, "record")["summary"]   # the existing page keeps its shape


def test_each_holding_carries_the_long_term_mark_from_the_marks_table(tmp_path):
    db = seed(tmp_path / "sp.duckdb")
    db.execute("insert into long_term_marks (symbol, marked_by) values ('WIPRO', 'owner')")
    out = tmp_path / "site"
    site.build(db, out, today=AS_OF, budget_inr=100000, now=__import__("datetime").datetime(2026, 11, 20, 19, 30), tokens=TOKENS)
    hs = {h["symbol"]: h for h in data(out, "portfolio")["holdings"]}
    assert hs["WIPRO"]["long_term"] is True
    assert all(h["long_term"] is False for s, h in hs.items() if s != "WIPRO")
