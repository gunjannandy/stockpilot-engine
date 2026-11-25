from conftest import load
from seed_site import AS_OF


def test_five_index_lines_each_with_a_sentence(built):
    ix = load(built, "indices")
    assert list(ix) == ["nifty", "bank", "mid", "small", "vix"]
    assert ix["nifty"]["name"] == "Nifty 50" and ix["vix"]["name"] == "India VIX"
    for v in ix.values():
        assert len(v["dates"]) == len(v["close"]) >= 2 and v["sentence"]
    assert ix["nifty"]["dates"] == sorted(ix["nifty"]["dates"])


def test_flows_say_who_is_buying(built):
    f = load(built, "flows")
    assert f["as_of"] == str(AS_OF) and {r["category"] for r in f["rows"]} == {"FII", "DII"}
    assert f["rows"] == sorted(f["rows"], key=lambda r: (r["date"], r["category"]))
    assert f["totals"]["FII"]["net_cr"] < 0 < f["totals"]["DII"]["net_cr"] and "sold" in f["sentence"]


def test_market_json_drops_the_stale_notes_and_carries_flows(built):
    m = load(built, "market")
    assert "flows_note" not in m and m["flows"]["sentence"]
    assert "bulk_deals_note" not in load(built, "watchlist")


def test_closed_trades(built):
    t = load(built, "trades_closed")
    assert t["closed"] == 2 and t["winners"] == 1 and t["losers"] == 1
    assert [r["symbol"] for r in t["rows"]] == ["ITC", "TCS"]       # newest sale first
    tcs = t["rows"][1]
    assert tcs["gain"] == 4000 and tcs["cost"] == 30000 and tcs["proceeds"] == 34000 and tcs["term"] == "long"
    assert t["total_gain"] == 4000 - 400 and t["sentence"]


def test_calls_with_outcomes(built):
    o = load(built, "calls_outcomes")
    assert o["rows"] and all(r["score_1m"] is not None or r["score_3m"] is not None or r["score_6m"] is not None for r in o["rows"])
    assert {"made_on", "symbol", "action", "probability", "outcome_3m"} <= set(o["rows"][0])
    assert o["sentence"]


def test_sell_kind_on_every_call(built):
    t = load(built, "today")
    wipro = t["sell"][0]
    assert wipro["symbol"] == "WIPRO" and wipro["sell_kind"] == "weak"       # a low chance alone is Weak
    assert all(c["sell_kind"] is None for c in t["buy"])
    calls = load(built, "calls")
    for c in calls["buys"] + calls["sells"] + calls["follow"]:
        assert "sell_kind" in c


def test_sell_kind_rules():
    from stockpilot.site_export import sell_kind
    assert sell_kind("sell", "sell") == "sell" and sell_kind("sell", "weak") == "weak" and sell_kind("sell", "review") == "review"
    assert sell_kind("trim", None) == "sell"                        # the size limit
    assert sell_kind("sell", None) == "weak"                        # an old call with no field: the cautious reading
    assert sell_kind("buy", "sell") is None and sell_kind("hold", None) is None



def test_unusual_today_signals(built):
    u = {r["symbol"]: {s["kind"] for s in r["signals"]} for r in load(built, "today")["unusual"]}
    assert "volume" in u["SBIN"]
    assert "corporate_action" in u["AXISBANK"]
    assert "results" in u["WIPRO"] and "watch_list_entry" in u["WIPRO"]
    assert "forecast_moved" in u["ICICIBANK"]
    assert all(s["text"] for r in load(built, "today")["unusual"] for s in r["signals"])


def test_since_last_time(built):
    s = load(built, "today")["since"]
    assert s["previous_on"] == "2026-11-19"
    assert "SUNPHARMA" in s["new"] and "M&M" in s["new"]
    assert s["changed"] == [{"symbol": "WIPRO", "from": "hold", "to": "sell"}]
    assert s["dropped"] == ["TATASTEEL"]
    assert s["moved"] == [{"symbol": "ICICIBANK", "from": 0.6, "to": 0.68}]
    assert s["sentence"]
