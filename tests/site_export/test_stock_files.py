"""Lane A: one history file and one stock file per searchable stock, with a plain sentence under every metric."""
import json

from conftest import load
from seed_site import AS_OF

JARGON = ("ASM", "GSM", "DMA", "50-day", "200-day", "VWAP", "RSI", "EBITDA", "stage ")


def sentences(obj):
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == "sentence":
                yield v
            else:
                yield from sentences(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from sentences(v)


def test_history_carries_volume_and_both_averages_and_older_weeks(built):
    h = load(built, "history/TCS")
    n = len(h["dates"])
    assert n == 250 == len(h["close"]) == len(h["volume"]) == len(h["dma50"]) == len(h["dma200"])
    assert h["dma50"][0] is None and h["dma50"][40] is not None and h["dma200"][-1] is not None and h["volume"][-1] == 2_000_000
    assert h["dma50"][-1] == round(sum(h["close"][-50:]) / 50, 2)
    assert h["older"]["dates"] and len(h["older"]["dates"]) == len(h["older"]["close"])
    assert h["older"]["dates"][-1] < h["dates"][0]


def test_every_search_stock_has_a_chart_and_key_numbers(built):
    search = load(built, "search")
    assert len(search) > 90
    for s in search:
        h = json.loads((built / "data" / "history" / f"{s['symbol']}.json").read_text())
        assert len(h["close"]) >= 2 and len(h["close"]) == len(h["dates"])
        k = json.loads((built / "data" / "stock" / f"{s['symbol']}.json").read_text())
        assert k["symbol"] == s["symbol"] and k["name"] and k["close"] > 0
        assert k["range52"]["low"] <= k["close"] <= k["range52"]["high"] and 0 <= k["range52"]["position"] <= 1
        assert k["volume"]["last"] > 0


def test_fifty_two_week_range_and_volume_sentences(built):
    k = load(built, "stock/SBIN")
    assert k["volume"]["ratio"] >= 3 and "usual" in k["volume"]["sentence"]
    r = k["range52"]
    assert "52-week" in r["sentence"] or "year" in r["sentence"]


def test_eight_quarters_and_three_years_summed_from_quarters(built):
    k = load(built, "stock/TCS")
    q = k["quarters"]
    assert len(q) == 8 and [x["period_end"] for x in q] == sorted(x["period_end"] for x in q)
    assert q[-1]["period_end"] == "2026-09-30"
    last = q[-1]
    assert last["sales_cr"] == 9999.0          # the restatement (newest filing) wins
    assert q[-2]["sales_cr"] != 1.0            # standalone never replaces consolidated
    y = k["yearly"]
    assert [x["fy"] for x in y] == ["FY2023-24", "FY2024-25", "FY2025-26"] and all(x["quarters"] == 4 for x in y)
    fy = [x for x in q if "2025-04-01" <= x["period_end"] <= "2026-03-31"]
    assert abs(sum(x["sales_cr"] for x in fy) - y[-1]["sales_cr"]) < 0.02


def test_a_stock_with_too_few_quarters_has_no_yearly_block(built):
    k = load(built, "stock/INFY")
    assert len(k["quarters"]) == 3 and "yearly" not in k


def test_delivery_headlines_deals_surveillance_results(built):
    k = load(built, "stock/TCS")
    assert 40 <= k["delivery"]["pct"] <= 50 and len(k["delivery"]["values"]) == len(k["delivery"]["dates"]) <= 60
    assert [h["title"] for h in k["headlines"]] == ["TCS wins a large deal", "TCS opens a new office", "Analysts update TCS targets"]
    assert [d["kind"] for d in k["deals"]] == ["bulk", "block"] and k["deals"][0]["date"] == "2026-11-17"
    assert k["results"]["next_on"] == "2026-12-10"
    a = load(built, "stock/ASMCO")["surveillance"]
    assert (a["scheme"], a["stage"]) == ("ASM", 2)
    w = load(built, "stock/WIPRO")["surveillance"]
    assert (w["scheme"], w["stage"]) == ("GSM", 4)
    assert "surveillance" not in load(built, "stock/ITC")


def test_announcements_of_the_last_month(built):
    k = load(built, "stock/SBIN")
    assert [a["subject"] for a in k["announcements"]] == ["Dividend of Rs 13 per share, record date 28 Nov"]


def test_nuance_paragraph_only_on_analysed_stocks(built):
    assert load(built, "stock/ICICIBANK")["analyst_note"].startswith("Earnings keep growing")
    assert "analyst_note" not in load(built, "stock/MPHASIS")


def test_every_sentence_is_plain_words(built):
    seen = 0
    for sym in ("TCS", "SBIN", "ASMCO", "WIPRO", "INFY", "ITC"):
        for s in sentences(load(built, f"stock/{sym}")):
            seen += 1
            assert isinstance(s, str) and 8 < len(s) < 220, s
            assert not any(j in s for j in JARGON), s
    assert seen > 12


def test_each_block_that_shows_a_number_has_a_sentence(built):
    k = load(built, "stock/TCS")
    for block in ("range52", "volume", "delivery", "quarters_note", "yearly_note", "deals_note"):
        assert (k[block] if block.endswith("_note") else k[block]["sentence"])


def test_ownership_is_the_latest_quarter_with_a_trend_and_no_future_filings(built):
    o = load(built, "stock/TCS")["ownership"]
    assert (o["quarter_end"], o["promoter_pct"], o["pledge_pct"]) == ("2026-09-30", 72.0, 6.5)
    assert o["change_pts"] == -0.4
    assert [(t["quarter_end"], t["promoter_pct"], t["pledge_pct"]) for t in o["trend"]] == [
        ("2025-09-30", 71.8, 0.0), ("2025-12-31", 71.8, 0.0), ("2026-03-31", 72.2, 0.0), ("2026-06-30", 72.4, 0.0), ("2026-09-30", 72.0, 6.5)]
    assert "72%" in o["sentence"] and "pledged" in o["sentence"] and "down" in o["sentence"]


def test_ownership_without_a_pledge_number_leaves_pledge_out_and_old_data_is_hidden(built):
    o = load(built, "stock/INFY")["ownership"]
    assert "pledge_pct" not in o and "change_pts" not in o and "pledge" not in o["sentence"]
    assert "pledge_pct" not in o["trend"][0]
    assert "ownership" not in load(built, "stock/ITC")          # newest quarter is over a year old
    assert "ownership" not in load(built, "stock/SBIN")         # never read


def test_files_of_symbols_that_are_no_longer_exported_are_removed(tmp_path):
    """A build used to leave old history and stock files behind (a series flagged since, a fund code): the schema check
    then failed on files nobody had written this time."""
    from datetime import datetime
    from seed_site import TOKENS
    from site_export_seed import seed
    from stockpilot import site
    NOW = datetime(2026, 11, 20, 19, 30)
    db = seed(tmp_path / "sp.duckdb")
    out = tmp_path / "site"
    site.build(db, out, today=AS_OF, budget_inr=100000, now=NOW, tokens=TOKENS)
    for sub in ("history", "stock"):
        (out / "data" / sub / "GONE.json").write_text('{"dates": [], "close": []}')
    site.build(db, out, today=AS_OF, budget_inr=100000, now=NOW, tokens=TOKENS)
    assert not (out / "data" / "history" / "GONE.json").exists() and not (out / "data" / "stock" / "GONE.json").exists()
    assert (out / "data" / "history" / "TCS.json").exists()
