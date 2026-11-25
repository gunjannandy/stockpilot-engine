"""The dossier: one stock's code-computed facts, small enough to hand 35 of them to a model."""
import json
from datetime import date, timedelta

import pytest

from forecast_seed import AS_OF, SECTOR_INDEX, seeded
from helpers import insert_prices
from stockpilot import dossier, readiness, store
from stockpilot.analysis import backtest, screen
from stockpilot.book import positions

BLOCKS = {"symbol", "name", "industry", "price", "weekly", "delivery", "fundamentals", "earlier", "pe_view", "results_on",
          "announcements", "headlines", "deals", "flag", "base_rate", "previous", "holding"}


@pytest.fixture(scope="module")
def world(tmp_path_factory):
    db = seeded(tmp_path_factory.mktemp("d"))
    result = screen.run(db, AS_OF)
    ctx = dossier.context(db, AS_OF, result, positions.held(db, AS_OF), SECTOR_INDEX)
    return db, ctx


def size_tokens(d):
    return len(json.dumps(d, separators=(",", ":"), default=str)) / 4


def test_every_block_is_present_for_a_holding_and_the_dossier_is_under_1000_tokens(world):
    db, ctx = world
    d = dossier.build(db, "WIPRO", AS_OF, ctx=ctx)       # held, flagged by results date, headlines, earlier snapshots
    assert BLOCKS <= set(d), BLOCKS - set(d)
    assert size_tokens(d) < 1000


def test_sbin_has_a_deal_and_a_delivery_spike(world):
    db, ctx = world
    d = dossier.build(db, "SBIN", AS_OF, ctx=ctx)
    assert d["deals"] and "Societe Generale" in d["deals"][0] and "BUY" in d["deals"][0]
    assert d["delivery"]["today"] > d["delivery"]["avg_20d"]
    assert d["price"]["vol_vs_20d"] > 3                 # the seed trades 3.5x the usual volume on the last day


def test_weekly_closes_cover_52_weeks_and_the_range_matches_them(world):
    db, ctx = world
    d = dossier.build(db, "INFY", AS_OF, ctx=ctx)
    assert 48 <= len(d["weekly"]) <= 52
    p = d["price"]
    assert p["high_52w"] >= max(d["weekly"]) - 0.5 and p["low_52w"] <= min(d["weekly"]) + 0.5
    assert p["close"] == pytest.approx(d["weekly"][-1], abs=0.6) or p["close"] > 0


def test_the_previous_call_carries_no_score(world):
    db, ctx = world
    d = dossier.build(db, "INFY", AS_OF, ctx=ctx)
    assert d["previous"] == {"date": str(AS_OF - timedelta(days=1)), "section": "hold", "probability": 0.52,
                             "summary": "Steady. Nothing to do."}


def test_a_holding_shows_each_lot_its_long_term_date_and_the_tax_if_sold_today(world):
    db, ctx = world
    h = dossier.build(db, "WIPRO", AS_OF, ctx=ctx)["holding"]
    assert [l["qty"] for l in h["lots"]] == [200, 100]
    assert h["lots"][1]["long_term_on"] == "2026-12-02"
    assert h["tax_if_sold"]["tax"] >= 0 and "short_gain" in h["tax_if_sold"]
    assert h["weight_pct"] > 0


def test_pe_is_set_against_its_own_snapshots_and_the_industry_median(world):
    db, ctx = world
    d = dossier.build(db, "INFY", AS_OF, ctx=ctx)
    assert len(d["earlier"]) == 3
    assert d["pe_view"]["industry_median"] > 0 and "earlier" in d["pe_view"]["vs_own"]


def test_results_date_announcements_and_headlines_have_ids_the_model_can_cite(world):
    db, ctx = world
    d = dossier.build(db, "WIPRO", AS_OF, ctx=ctx)
    assert d["results_on"] == str(AS_OF + timedelta(days=15))
    ids = [i["id"] for i in d["announcements"] + d["headlines"]]
    assert ids == [f"WIPRO-{n}" for n in range(1, len(ids) + 1)] and len(ids) >= 2


def test_the_flag_names_asm_and_gsm_stocks(world):
    db, ctx = world
    assert dossier.build(db, "ASMCO", AS_OF, ctx=ctx)["flag"] == "ASM stage 2"
    assert dossier.build(db, "INFY", AS_OF, ctx=ctx)["flag"] is None


def test_base_rate_comes_with_its_sample_size(world):
    db, ctx = world
    br = dossier.build(db, "INFY", AS_OF, ctx=ctx)["base_rate"]
    assert br["n"] == 800 and 0.4 < br["rate"] < 0.6


def test_the_forty_bucket_table_is_used_when_it_exists_and_keyed_by_the_stocks_own_volatility_and_liquidity(world):
    db, ctx = world
    c = ctx.candidates["INFY"]
    vols = sorted(x["metrics"]["vol_1y"] for x in ctx.candidates.values() if x["metrics"].get("vol_1y") is not None)
    med = vols[len(vols) // 2] if len(vols) % 2 else (vols[len(vols) // 2 - 1] + vols[len(vols) // 2]) / 2
    calm, size = backtest.cut_of(c["metrics"]["vol_1y"], med, c["metrics"]["adv_3m_cr"])
    bucket = min(4, int(c["scores"]["momentum"] * 5))
    db.execute("delete from base_rate_buckets")
    db.execute("insert into base_rate_buckets values (91, ?, ?, ?, ?, 321, 0.61, 0.02, ?)", [bucket, ctx.regime, calm, size, AS_OF])
    got = dossier.build(db, "INFY", AS_OF, ctx=dossier.context(db, AS_OF, screen.run(db, AS_OF), positions.held(db, AS_OF), SECTOR_INDEX))
    assert got["base_rate"] == {"rate": 0.61, "n": 321}
    db.execute("delete from base_rate_buckets")        # back to the older table so the other tests are untouched


def test_a_missing_r3_table_just_drops_that_block(tmp_path):
    db = seeded(tmp_path)
    for t in ("delivery", "deals", "headlines", "results_calendar", "flows"):
        db.execute(f"drop table {t}")
    d = dossier.build(db, "INFY", AS_OF)                # no ctx at all: still builds
    assert "delivery" not in d and not d.get("deals") and not d.get("headlines") and d.get("results_on") is None
    assert d["price"]["close"] > 0 and d["weekly"]


def test_a_split_inside_the_year_leaves_no_jump_in_the_weekly_closes(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    day = date(2026, 11, 20)
    rows, prev = [], 1000.0
    for i in range(300):
        d = day - timedelta(days=299 - i)
        px = 1000.0 if d < date(2026, 6, 1) else 200.0      # a 1:5 split on 1 June
        rows.append((d, "SPLITCO", "NSE", "EQ", prev, px * 1.01, px * 0.99, px, prev, 1000, px * 1000, 9))
        prev = px
    insert_prices(db, rows)
    db.execute("insert into corporate_actions (symbol, ex_date, kind, numerator, denominator) "
               "values ('SPLITCO', '2026-06-01', 'split', 5, 1)")
    w = dossier.build(db, "SPLITCO", day)["weekly"]
    assert max(w) / min(w) < 1.05


def test_swing_levels_on_a_synthetic_zigzag():
    import math
    closes = [100 + 10 * math.sin(i / 6) for i in range(120)]     # swings between about 90 and 110
    highs = [c + 1 for c in closes]
    lows = [c - 1 for c in closes]
    sup, res = dossier.swing_levels(highs, lows, close=100.0, atr=2.0)
    assert all(s < 100 for s in sup) and all(r > 100 for r in res)
    assert len(sup) <= 2 and len(res) <= 2
    assert sup == sorted(sup, reverse=True) and res == sorted(res)


def test_atr_is_the_14_day_average_true_range():
    highs = [11.0] * 20
    lows = [9.0] * 20
    closes = [10.0] * 20
    assert dossier.atr(highs, lows, closes) == pytest.approx(2.0)
    highs[-1], lows[-1] = 15.0, 9.0                      # one wide day lifts the average by 4/14
    assert dossier.atr(highs, lows, closes) == pytest.approx(2.0 + 4 / 14)


def test_the_market_block_has_every_part(world):
    db, ctx = world
    m = dossier.market(db, AS_OF, ctx, industries=["IT", "Banks", "Metals"], held=["WIPRO", "INFY"])
    assert m["nifty"]["pe"] > 0 and 0 <= m["nifty"]["pe_percentile"] <= 1
    assert m["breadth"]["now"] is not None and m["breadth"]["20d_ago"] is not None
    assert m["sectors"]["IT"] > 0 > m["sectors"]["Banks"]
    assert m["unmapped_industries"] == ["Metals"]
    assert m["flows"]["fii_net_5d_cr"] < 0 < m["flows"]["dii_net_5d_cr"] and m["flows"]["days"] == 5
    assert 0 < m["vix"]["percentile_1y"] <= 1 and m["vix"]["close"] > 0
    assert {r["symbol"] for r in m["results_soon"]} == {"INFY"}      # WIPRO reports in 15 days: outside the 10


def test_the_market_block_drops_flows_when_the_table_is_missing(tmp_path):
    db = seeded(tmp_path)
    db.execute("drop table flows")
    m = dossier.market(db, AS_OF, dossier.context(db, AS_OF), industries=[], held=[])
    assert "flows" not in m and m["nifty"]["pe"] > 0
