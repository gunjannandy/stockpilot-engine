"""The seeded site DB plus the sources lane R3 builds (delivery, deals, results calendar, flows, headlines), the
base rates and the sector indices the forecaster reads. Tables R3 owns are created here only when they are missing."""
import json
from datetime import date, datetime, timedelta

from seed_site import AS_OF, seed as seed_site
from stockpilot import readiness

R3_TABLES = [
    "create table delivery (date date, symbol varchar, series varchar, deliv_qty double, deliv_pct double)",
    "create table deals (date date, symbol varchar, kind varchar, client varchar, side varchar, quantity double, price double)",
    "create table results_calendar (symbol varchar, date date, purpose varchar, detail varchar)",
    "create table flows (date date, category varchar, buy_cr double, sell_cr double, net_cr double)",
    "create table headlines (symbol varchar, published_at timestamp, title varchar, source varchar, url varchar, fetched_on date)",
]
SECTOR_INDEX = {"IT": "Nifty IT", "Banks": "Nifty Bank", "Auto": "Nifty Auto", "Pharma": "Nifty Pharma", "FMCG": "Nifty FMCG"}


def business_days(end, n):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def add_sources(db, day=AS_OF):
    for sql in R3_TABLES:
        name = sql.split()[2]
        if not readiness.has_table(db, name):
            db.execute(sql)
    days = business_days(day, 30)
    for n, d in enumerate(days):
        for sym in ("INFY", "SBIN", "WIPRO", "TCS", "ICICIBANK"):
            db.execute("insert into delivery values (?, ?, 'EQ', 100000, ?)", [d, sym, 40 + (n % 5) * 3 + (15 if d == day and sym == "SBIN" else 0)])
        if n >= 25:
            db.execute("insert into flows values (?, 'FII', 9000, 11000, ?)", [d, -2000 - n])
            db.execute("insert into flows values (?, 'DII', 11000, 9500, 1500)", [d])
    db.execute("insert into deals values (?, 'SBIN', 'bulk', 'Societe Generale', 'BUY', 4500000, 812.5)", [day - timedelta(days=6)])
    db.execute("insert into results_calendar values ('WIPRO', ?, 'Financial Results', 'Q2')", [day + timedelta(days=15)])
    db.execute("insert into results_calendar values ('INFY', ?, 'Financial Results', 'Q2')", [day + timedelta(days=6)])
    db.execute("insert into results_calendar values ('TCS', ?, 'Financial Results', 'Q2')", [day + timedelta(days=3)])
    for sym, title in (("INFY", "Infosys wins a large deal in Europe"), ("SBIN", "SBI raises lending rates"), ("WIPRO", "Wipro cuts guidance")):
        db.execute("insert into headlines values (?, ?, ?, 'Economic Times', 'https://x/y', ?)",
                   [sym, datetime.combine(day - timedelta(days=2), datetime.min.time()), title, day])
    # earlier fundamentals snapshots, so P/E can be set against its own history
    for k, sym in enumerate(("INFY", "SBIN", "WIPRO", "TCS")):
        for weeks, pe in ((8, 20), (4, 22), (1, 25)):
            db.execute("insert into fundamentals values (?, ?, 'pe', ?, 'yahoo')", [day - timedelta(weeks=weeks), sym, pe + k])
    for b in range(5):
        for regime in ("nifty_up", "nifty_down"):
            db.execute("insert into base_rates values ('momentum', ?, ?, 91, 800, ?, 0.01, ?)",
                       [b, regime, 0.44 + 0.03 * b, day])
    # sector indices (3 months of rising IT, falling banks) and the India VIX
    for n, d in enumerate(business_days(day, 300)):
        for name, drift in (("Nifty IT", 0.0015), ("Nifty Bank", -0.0015), ("Nifty Auto", 0.0003), ("Nifty Pharma", 0.0002),
                            ("Nifty FMCG", 0.0001)):
            db.execute("insert into index_levels values (?, ?, ?, 20, 3, 1)", [d, name, 1000 * (1 + drift) ** n])
        db.execute("insert into index_levels values (?, 'India VIX', ?, null, null, null)", [d, 12 + (n % 60) / 6])
    db.execute("insert into calls (made_on, symbol, kind, action, section, probability, base_rate, reasons, score_1m, score_3m) "
               "values (?, 'INFY', 'holding', 'hold', 'hold', 0.52, 0.5, ?, 1.0, 1.0)",
               [day - timedelta(days=1), json.dumps({"summary": "Steady. Nothing to do."})])
    return db


def seeded(tmp_path):
    return add_sources(seed_site(tmp_path / "sp.duckdb"))
