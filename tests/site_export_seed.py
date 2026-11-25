"""The seeded site DB plus the rows lane A exports (all invented: no real names, numbers or documents)."""
import json
from datetime import date, datetime, timedelta

from seed_site import AS_OF, seed as base_seed


def _q(db, sym, end, rev, op, net, filed, consolidated=True):
    db.execute("insert into quarterly (isin, symbol, period_end, consolidated, filed_at, revenue, operating_profit, "
               "net_profit, eps) values (?, ?, ?, ?, ?, ?, ?, ?, 1)", ["INE" + sym[:6].ljust(6, "0") + "01", sym, end, consolidated, filed, rev * 1e7, op * 1e7, net * 1e7])   # figures in crore, stored in rupees


def _quarter_ends(n, last=date(2026, 9, 30)):
    """The last day of each of n quarters ending at `last`, oldest first."""
    ends, y, m = [], last.year, last.month
    for _ in range(n):
        ends.append(date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
        m -= 3
        if m < 1:
            m, y = m + 12, y - 1
    return ends[::-1]


def seed(path):
    db = base_seed(path)
    for end in _quarter_ends(14):      # 14 quarters ending Sep 2026 for TCS; two stocks with fewer
        k = (end.year - 2023) * 4 + end.month // 3
        _q(db, "TCS", end, 1000 + 10 * k, 250 + 2 * k, 200 + k, datetime(end.year, end.month, 28) + timedelta(days=40))
    _q(db, "TCS", date(2026, 9, 30), 9999, 2500, 2000, datetime(2026, 11, 15), True)     # a restatement: newest filing wins
    _q(db, "TCS", date(2026, 6, 30), 1, 1, 1, datetime(2026, 8, 1), False)                # standalone never beats consolidated
    for end in _quarter_ends(3):
        _q(db, "INFY", end, 500, 100, 80, datetime(end.year, end.month, 28) + timedelta(days=40))
    for n in range(40):
        day = AS_OF - timedelta(days=n)
        if day.weekday() < 5:
            db.execute("insert into delivery values (?, 'TCS', 'EQ', 500000, ?)", [day, 40 + (n % 10)])
    db.execute("insert into deals values (?, 'TCS', 'bulk', 'Example Fund A', 'buy', 1200000, 3500.5), "
               "(?, 'TCS', 'block', 'Example Fund B', 'sell', 900000, 3490.0), (?, 'TCS', 'bulk', 'Old Fund', 'buy', 5, 1)",
               [AS_OF - timedelta(days=3), AS_OF - timedelta(days=10), AS_OF - timedelta(days=60)])
    for n, title in [(2, "TCS wins a large deal"), (12, "TCS opens a new office"), (29, "Analysts update TCS targets"), (50, "Old TCS story")]:
        db.execute("insert into headlines values ('TCS', ?, ?, 'Example Wire', ?, ?)",
                   [datetime.combine(AS_OF - timedelta(days=n), datetime.min.time()), title, f"https://example.test/{n}", AS_OF])
    for q, promoter, pledge, filed in [(date(2025, 9, 30), 71.8, 0.0, date(2025, 11, 5)), (date(2025, 12, 31), 71.8, 0.0, date(2026, 2, 6)),
                                       (date(2026, 3, 31), 72.2, 0.0, date(2026, 5, 6)), (date(2026, 6, 30), 72.4, 0.0, date(2026, 8, 5)),
                                       (date(2026, 9, 30), 72.0, 6.5, date(2026, 11, 4)), (date(2026, 12, 31), 99.0, 99.0, date(2027, 2, 4))]:
        db.execute("insert into ownership values ('TCS', ?, ?, ?, ?, null, ?, true)", [q, promoter, round(100 - promoter, 2), pledge, filed])
    db.execute("insert into ownership values ('INFY', '2026-09-30', 14.9, 85.1, null, null, '2026-11-04', true)")        # pledge unknown
    db.execute("insert into ownership values ('ITC', '2024-06-30', 0.0, 100.0, 0.0, null, '2024-08-05', true)")          # too old to show
    db.execute("insert into watchlist (symbol, exchange, added_by) values ('ASMCO', 'NSE', 'import')")   # watched, though the screen excludes it
    db.execute("insert into surveillance values (?, 'WIPRO', 'GSM stage 4')", [AS_OF])
    db.execute("insert into surveillance values (?, 'ASMCO', 'ASM stage 2')", [AS_OF - timedelta(days=1)])   # WIPRO entered today
    db.execute("insert into results_calendar values ('TCS', ?, 'Financial Results', ''), ('TCS', ?, 'Financial Results', '')",
               [AS_OF + timedelta(days=20), AS_OF - timedelta(days=70)])
    for n in range(6):
        day = AS_OF - timedelta(days=n)
        db.execute("insert into flows values (?, 'FII', 1000, 1200, ?), (?, 'DII', 1500, 1300, ?)", [day, -200 - n, day, 200 + n])
    for name, base in [("Nifty Bank", 44000), ("NIFTY Midcap 100", 50000), ("Nifty Smallcap 250", 15000), ("India VIX", 13)]:
        for n in range(30):
            db.execute("insert into index_levels values (?, ?, ?, null, null, null)", [AS_OF - timedelta(days=n), name, base + n])
    for sym, bought, qty, cost, sold, price in [("TCS", date(2025, 1, 10), 10, 3000, date(2026, 3, 10), 3400),
                                                ("ITC", date(2026, 1, 5), 20, 400, date(2026, 5, 5), 380)]:
        isin = "INE" + sym[:6].ljust(6, "0") + "01"
        db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, closed_quantity, source) "
                   "values ('equity', ?, ?, ?, ?, ?, ?, 'tradebook')", [sym, isin, bought, qty, cost, qty])
        db.execute("insert into sales (kind, symbol, isin, sold_on, quantity, price_per_unit, source) values ('equity', ?, ?, ?, ?, ?, 'tradebook')",
                   [sym, isin, sold, qty, price])
    # yesterday's calls (for the `since` block): WIPRO was a hold, ICICIBANK a buy at a lower chance, SUNPHARMA absent, TATASTEEL a buy that was dropped
    prev = AS_OF - timedelta(days=1)
    for sym, kind, action, p in [("WIPRO", "holding", "hold", 0.5), ("ICICIBANK", "candidate", "buy", 0.60), ("TATASTEEL", "candidate", "buy", 0.62)]:
        db.execute("insert into calls (made_on, symbol, kind, action, probability, base_rate, horizon_days, entry, stop, target, size_inr, reasons, "
                   "risks, news, runner, unproven) values (?, ?, ?, ?, ?, 0.5, 91, 100, 90, 120, 0, '{}', '[]', '[]', 'claude', true)",
                   [prev, sym, kind, action, p])
    db.execute("update calls set section = case symbol when 'ICICIBANK' then 'buy' when 'WIPRO' then 'sell' when 'SBIN' then 'follow' end "
               "where made_on = ? and symbol in ('ICICIBANK', 'WIPRO', 'SBIN')", [AS_OF])        # the forecaster's sections (calls.json)
    # lane F1: what the reasoning object reads from a stored call (the forecaster stores these; levels' hit rate comes from lane F3)
    db.execute("update calls set base_rate_n = 3637, hurdle = 0.02, would_buy_if = 'A close above its 50-day average.', "
               "level_flag = 'Results fall before the target date.', change_reason = 'Its chance rose from 60% to 68%.', "
               "reasons = json_merge_patch(reasons::json, ?::json) where made_on = ? and symbol = 'ICICIBANK'",
               [json.dumps({"target_hit_rate": 0.52, "target_hit_n": 1800,
                            "levels_why": "If it falls to ₹90 (just under its recent low of ₹95), sell. Aim for ₹120 (its recent high of ₹120).",
                            "for": [{"text": "Profit grew 12% in the last quarter", "area": "growth", "weight": 1.5, "news_used": ["N1"]}],
                            "against": [{"text": "The price is near its yearly high", "area": "trend", "weight": -1.0, "news_used": ["N1"]}]}), AS_OF])
    db.execute("update calls set base_rate_n = 12 where made_on = ? and symbol = 'WIPRO'", [AS_OF])        # a thin base rate
    return db


def add_universe(db, n=1500, days=270):
    """n more invented stocks (bulk-inserted), so the universe is as long as the real one (about 1,617)."""
    import random

    from helpers import insert_prices
    from seed_site import _business_days
    rng, rows = random.Random(3), []
    for i in range(n):
        sym = f"ZZ{i:04d}"
        db.execute("insert into stocks values (?, ?, 'Misc', ?)", [sym, f"Invented Company {i}", f"INE{i:06d}01"])
        price = 100 + rng.random() * 400
        for d in _business_days(AS_OF, days):
            prev, price = price, max(5.0, price * (1 + rng.gauss(0.0003, 0.015)))
            rows.append((d, sym, "NSE", "EQ", prev, price, price, price, prev, 800_000, price * 800_000, 4000))
        for metric, value in {"pe": 20, "pb": 3, "roe": 0.15, "roce": 0.18, "debt_to_equity": 0.4, "profit_cagr_3y": 0.1}.items():
            db.execute("insert into fundamentals values (?, ?, ?, ?, 'yahoo')", [AS_OF, sym, metric, value])
    insert_prices(db, rows)
