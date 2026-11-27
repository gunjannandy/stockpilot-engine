"""Lane E: the three blocks the analyst reasons from: company history, market gravity, news. Code works out the facts from
data on file; a block with nothing to say is left out (the gap is the Health tab's, not the father's)."""
import json
from datetime import date, datetime, timedelta

import pytest

from helpers import insert_prices
from stockpilot import dossier, dossier_blocks as blocks, store

DAY = date(2026, 11, 20)


@pytest.fixture
def db(tmp_path):
    d = store.open(tmp_path / "b.duckdb")
    d.execute("insert into stocks values ('ACME', 'Acme Ltd', 'Banks', 'INE000A01010')")
    for sym in ("AAA", "BBB", "CCC"):
        d.execute("insert into stocks values (?, ?, 'Banks', ?)", [sym, sym, "INE" + sym])
    return d


def weekly_rows(symbol, closes, start=date(2016, 11, 21), exchange="NSE"):
    """One Friday close a week; the other columns are flat."""
    out = []
    for n, c in enumerate(closes):
        d = start + timedelta(weeks=n, days=4)
        out.append((d, symbol, exchange, "EQ", c, c, c, c, c, 1000, 1000 * c, 10))
    return out


def prices_cols_ok(db):
    return [r[0] for r in db.execute("describe prices").fetchall()]


def quarter(db, symbol, period_end, revenue, profit):
    db.execute("insert into quarterly values (null, ?, ?, true, ?, ?, null, ?, 1.0, 'u')",
               [symbol, period_end, datetime.combine(period_end + timedelta(days=40), datetime.min.time()), revenue * 1e7, profit * 1e7])


def fund(db, symbol, metric, value, as_of=DAY):
    db.execute("insert into fundamentals values (?, ?, ?, ?, 'yahoo')", [as_of, symbol, metric, value])


# ---- history -------------------------------------------------------------------------------------------------

def test_yearly_results_sum_four_complete_quarters_per_financial_year_newest_first(db):
    for fy in (2023, 2024, 2025):
        for m, y in ((6, fy - 1), (9, fy - 1), (12, fy - 1), (3, fy)):
            quarter(db, "ACME", date(y, m, 30 if m in (6, 9) else 31), 100 * (fy - 2022), 10 * (fy - 2022))
    quarter(db, "ACME", date(2025, 6, 30), 999, 99)        # FY2026 has one quarter only: not a year
    h = blocks.history(db, "ACME", DAY)
    assert [y["fy"] for y in h["yearly"]] == ["FY2025", "FY2024", "FY2023"]
    assert h["yearly"][0] == {"fy": "FY2025", "revenue_cr": 1200.0, "profit_cr": 120.0}
    assert h["profit_trend"] == "Profit rose in 2 of the last 2 years."


def test_a_profit_that_fell_is_said_plainly(db):
    for fy, profit in ((2023, 50), (2024, 80), (2025, 60)):
        for m, y in ((6, fy - 1), (9, fy - 1), (12, fy - 1), (3, fy)):
            quarter(db, "ACME", date(y, m, 30 if m in (6, 9) else 31), 100, profit / 4)
    assert blocks.history(db, "ACME", DAY)["profit_trend"] == "Profit rose in 1 of the last 2 years."


def test_at_most_ten_years_are_kept(db):
    for fy in range(2012, 2026):
        for m, y in ((6, fy - 1), (9, fy - 1), (12, fy - 1), (3, fy)):
            quarter(db, "ACME", date(y, m, 30 if m in (6, 9) else 31), 100, 10)
    assert len(blocks.history(db, "ACME", DAY)["yearly"]) == 10


def test_a_past_fall_shows_how_deep_how_long_and_what_the_market_did(db):
    # 520 weeks: climb 100->200, fall to 120 (-40%), climb back past 200
    closes = [100 + i for i in range(100)] + [200 - 2 * i for i in range(40)] + [120 + 2 * i for i in range(60)] + [240] * 320
    insert_prices(db, weekly_rows("ACME", closes))
    h = blocks.history(db, "ACME", DAY)
    fall = h["falls"][0]
    assert fall["fall_pct"] == -40 and fall["recovered_after_weeks"] is not None and fall["recovered_after_weeks"] > 40
    assert h["years_on_record"] >= 9.9


def test_a_fall_that_has_not_recovered_says_so(db):
    closes = [100 + i for i in range(100)] + [199 - 2 * i for i in range(60)]
    insert_prices(db, weekly_rows("ACME", closes, start=DAY - timedelta(weeks=len(closes))))
    assert blocks.history(db, "ACME", DAY)["falls"][0]["recovered_after_weeks"] is None


def test_small_dips_are_not_falls(db):
    closes = [100, 105, 98, 110, 104, 120] * 30
    insert_prices(db, weekly_rows("ACME", closes, start=DAY - timedelta(weeks=len(closes))))
    assert "falls" not in blocks.history(db, "ACME", DAY)


def test_no_history_leaves_the_block_out(db):
    assert blocks.history(db, "ACME", DAY) == {}


# ---- gravity -------------------------------------------------------------------------------------------------

def test_gravity_gives_size_rank_owners_and_liquidity(db):
    for sym, cap in (("ACME", 5e11), ("AAA", 9e11), ("BBB", 1e11), ("CCC", 2e11)):
        fund(db, sym, "market_cap", cap)
    fund(db, "ACME", "insiders_pct", 0.52)
    g = blocks.gravity(db, "ACME", DAY, {"liquidity_cr": 180.0, "ret_3m": 0.10, "vs_sector_3m": 0.04}, "Banks", ranks=blocks.size_ranks(db, DAY))
    assert g["market_cap_cr"] == 50000.0 and g["size_rank"] == "2 of 4 stocks we follow"
    assert g["owners"] == {"insiders_pct": 52.0}
    assert g["liquidity"] == "very liquid (about ₹180 crore traded a day)"
    assert g["sector"] == {"name": "Banks", "vs_sector_3m_points": 4.0}


def test_a_thin_stock_is_called_thin(db):
    g = blocks.gravity(db, "ACME", DAY, {"liquidity_cr": 3.0}, "Banks", ranks={})
    assert g["liquidity"].startswith("thin")


def test_gravity_with_nothing_is_empty(db):
    assert blocks.gravity(db, "ACME", DAY, {}, None, ranks={}) == {}


# ---- news ----------------------------------------------------------------------------------------------------

def test_news_pairs_the_biggest_one_day_moves_with_what_was_said_that_day(db):
    closes = [100.0] * 30
    closes[20] = 108.0               # +8% on day index 20
    rows = []
    for n, c in enumerate(closes):
        d = DAY - timedelta(days=len(closes) - 1 - n)
        rows.append((d, "ACME", "NSE", "EQ", c, c, c, c, closes[n - 1] if n else c, 1000, 1000 * c, 10))
    insert_prices(db, rows)
    moved_on = DAY - timedelta(days=len(closes) - 1 - 20)
    db.execute("insert into announcements values (?, 'ACME', 'Wins a large order', null, null)", [datetime.combine(moved_on, datetime.min.time())])
    n = blocks.news(db, "ACME", DAY, [{"id": "ACME-1", "date": str(moved_on), "subject": "Wins a large order"}], [])
    assert n["moves"][0]["pct"] == 8.0 and n["moves"][0]["date"] == str(moved_on)
    assert n["moves"][0]["said"] == ["ACME-1"]


def test_a_move_with_nothing_said_still_shows_and_says_so(db):
    rows = [(DAY - timedelta(days=29 - n), "ACME", "NSE", "EQ", c, c, c, c, c, 1000, 1000 * c, 10)
            for n, c in enumerate([100.0] * 29 + [93.0])]
    insert_prices(db, rows)
    n = blocks.news(db, "ACME", DAY, [], [])
    assert n["moves"][0]["pct"] == -7.0 and n["moves"][0]["said"] == []


def test_news_carries_the_sector_and_the_market_for_the_month(db):
    for n in range(40):
        d = DAY - timedelta(days=39 - n)
        db.execute("insert into index_levels values (?, 'Nifty Bank', ?, null, null, null)", [d, 100 + n])
        db.execute("insert into index_levels values (?, 'Nifty 50', ?, null, null, null)", [d, 1000 - n])
    n = blocks.news(db, "ACME", DAY, [], [], sector_index="Nifty Bank")
    assert n["sector_1m_pct"] > 0 and n["market_1m_pct"] < 0


def test_a_quiet_month_leaves_the_news_block_out(db):
    assert blocks.news(db, "ACME", DAY, [], []) == {}


# ---- in the dossier ------------------------------------------------------------------------------------------

def test_the_dossier_carries_the_three_blocks_when_there_is_data(db):
    closes = [100 + i for i in range(100)] + [199 - 2 * i for i in range(60)]
    insert_prices(db, weekly_rows("ACME", closes, start=DAY - timedelta(weeks=len(closes))))
    fund(db, "ACME", "market_cap", 5e11)
    d = dossier.build(db, "ACME", DAY)
    assert {"history", "gravity"} <= set(d) and "falls" in d["history"] and "size_rank" in d["gravity"]
    assert len(json.dumps(d, default=str)) / 4 < 1800        # tokens: the three blocks stay small
