"""A seeded temp DB of realistic data for the dashboard: 14 stocks, a year of prices, calls, holdings, lots."""
import json
import random
from datetime import date, datetime, timedelta

import pandas as pd

from helpers import insert_prices
from stockpilot import store
from stockpilot.analysis import tax

AS_OF = date(2026, 11, 20)
_BASE = [  # symbol, name, industry, drift per day, pe, roe   (the first 14 keep their old numbers)
    ("TCS", "Tata Consultancy Services", "IT", 0.0007, 27, 0.46), ("INFY", "Infosys", "IT", 0.0004, 24, 0.31),
    ("WIPRO", "Wipro", "IT", -0.0003, 19, 0.17), ("HDFCBANK", "HDFC Bank", "Banks", 0.0006, 18, 0.16),
    ("ICICIBANK", "ICICI Bank", "Banks", 0.0008, 17, 0.18), ("SBIN", "State Bank of India", "Banks", 0.0005, 10, 0.17),
    ("AXISBANK", "Axis Bank", "Banks", -0.0002, 13, 0.14), ("MARUTI", "Maruti Suzuki", "Auto", 0.0003, 28, 0.15),
    ("TATAMOTORS", "Tata Motors", "Auto", -0.0006, 8, 0.25), ("M&M", "Mahindra & Mahindra", "Auto", 0.0009, 24, 0.19),
    ("SUNPHARMA", "Sun Pharma", "Pharma", 0.0006, 33, 0.16), ("CIPLA", "Cipla", "Pharma", 0.0002, 26, 0.15),
    ("ITC", "ITC", "FMCG", 0.0001, 25, 0.28), ("ASMCO", "Risky Metals", "Metals", 0.0004, 15, 0.12),
]
# more real NSE names, so the lists are as long as the father's real ones
_MORE = {
    "IT": "HCLTECH:HCL Technologies,TECHM:Tech Mahindra,LTIM:LTIMindtree,PERSISTENT:Persistent Systems,COFORGE:Coforge,MPHASIS:Mphasis,OFSS:Oracle Financial Services,KPITTECH:KPIT Technologies,CYIENT:Cyient",
    "Banks": "KOTAKBANK:Kotak Mahindra Bank,INDUSINDBK:IndusInd Bank,BANKBARODA:Bank of Baroda,PNB:Punjab National Bank,FEDERALBNK:Federal Bank,IDFCFIRSTB:IDFC First Bank,AUBANK:AU Small Finance Bank,CANBK:Canara Bank",
    "Financials": "BAJFINANCE:Bajaj Finance,BAJAJFINSV:Bajaj Finserv,CHOLAFIN:Cholamandalam Investment,SBILIFE:SBI Life Insurance,HDFCLIFE:HDFC Life Insurance,ICICIGI:ICICI Lombard,MUTHOOTFIN:Muthoot Finance,PFC:Power Finance Corporation,RECLTD:REC,LICHSGFIN:LIC Housing Finance,SHRIRAMFIN:Shriram Finance,M&MFIN:Mahindra Finance",
    "Auto": "BAJAJ-AUTO:Bajaj Auto,EICHERMOT:Eicher Motors,HEROMOTOCO:Hero MotoCorp,TVSMOTOR:TVS Motor,ASHOKLEY:Ashok Leyland,BOSCHLTD:Bosch,MOTHERSON:Samvardhana Motherson,BHARATFORG:Bharat Forge,MRF:MRF",
    "Pharma": "DRREDDY:Dr Reddy's Laboratories,DIVISLAB:Divi's Laboratories,LUPIN:Lupin,AUROPHARMA:Aurobindo Pharma,TORNTPHARM:Torrent Pharma,ZYDUSLIFE:Zydus Lifesciences,ALKEM:Alkem Laboratories,APOLLOHOSP:Apollo Hospitals,MAXHEALTH:Max Healthcare,BIOCON:Biocon",
    "FMCG": "HINDUNILVR:Hindustan Unilever,NESTLEIND:Nestle India,BRITANNIA:Britannia,DABUR:Dabur,MARICO:Marico,GODREJCP:Godrej Consumer,COLPAL:Colgate-Palmolive India,TATACONSUM:Tata Consumer,VBL:Varun Beverages,PIDILITIND:Pidilite,ASIANPAINT:Asian Paints",
    "Metals": "TATASTEEL:Tata Steel,JSWSTEEL:JSW Steel,HINDALCO:Hindalco,VEDL:Vedanta,NMDC:NMDC,SAIL:SAIL,JINDALSTEL:Jindal Steel,NATIONALUM:NALCO,APLAPOLLO:APL Apollo Tubes,HINDZINC:Hindustan Zinc",
    "Energy": "RELIANCE:Reliance Industries,ONGC:ONGC,NTPC:NTPC,POWERGRID:Power Grid,BPCL:BPCL,IOC:Indian Oil,GAIL:GAIL,TATAPOWER:Tata Power,ADANIGREEN:Adani Green,COALINDIA:Coal India,OIL:Oil India,PETRONET:Petronet LNG",
    "Capital goods": "LT:Larsen & Toubro,SIEMENS:Siemens,ABB:ABB India,BHEL:BHEL,HAL:Hindustan Aeronautics,BEL:Bharat Electronics,CUMMINSIND:Cummins India,POLYCAB:Polycab,HAVELLS:Havells,ADANIPORTS:Adani Ports",
    "Cement and property": "ULTRACEMCO:UltraTech Cement,GRASIM:Grasim,AMBUJACEM:Ambuja Cements,SHREECEM:Shree Cement,DLF:DLF,GODREJPROP:Godrej Properties,OBEROIRLTY:Oberoi Realty,LODHA:Macrotech Developers",
    "Consumer and telecom": "BHARTIARTL:Bharti Airtel,TITAN:Titan,TRENT:Trent,DMART:Avenue Supermarts,ZOMATO:Zomato,NAUKRI:Info Edge,INDIGO:InterGlobe Aviation,IRCTC:IRCTC,JUBLFOOD:Jubilant FoodWorks,PAGEIND:Page Industries,VOLTAS:Voltas,INDUSTOWER:Indus Towers",
}


def _universe():
    rng, out = random.Random(11), list(_BASE)
    for industry, packed in _MORE.items():
        for item in packed.split(","):
            sym, name = item.split(":")
            out.append((sym, name, industry, round(rng.uniform(-0.0006, 0.001), 5), rng.randint(9, 45),
                        round(rng.uniform(0.08, 0.32), 3)))
    return out


TOKENS = [{"name": "Claude login", "expires_on": "2027-10-01"}, {"name": "Kite", "expires_on": "2026-11-23"}]   # what config gives site.build
STOCKS = _universe()


def _h(sym):   # a stable small number per symbol (hash() changes every run)
    return sum(map(ord, sym))
HELD = ["INFY", "WIPRO", "TATAMOTORS", "HDFCBANK", "ITC", "RELIANCE", "LT", "BHARTIARTL", "TATASTEEL", "MARUTI",
        "NTPC", "COALINDIA", "BAJFINANCE", "TITAN", "CIPLA"]
# the father's real watchlist is 133 names; 130 here, with a few kept on both NSE and BSE the way imports do
_pick = random.Random(5)
WATCH = sorted({"TCS", "SBIN", "WIPRO", "ITC", "CIPLA", "SUNPHARMA", "AXISBANK", "M&M"}
               | set(_pick.sample([s[0] for s in STOCKS if s[0] not in ("ASMCO", "ZOMATO")], 122)))


def _walk(seed, drift, days):
    rng, price, out = random.Random(seed), 500.0 + seed * 40, []
    for _ in range(days):
        prev = price
        price = max(20.0, price * (1 + drift + rng.gauss(0, 0.012)))
        out.append((prev, price))
    return out


def _business_days(end, n):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def seed(path):
    db = store.open(path)
    days = _business_days(AS_OF, 270)
    rows, last = [], {}
    for i, (sym, *_rest) in enumerate(STOCKS):
        drift = STOCKS[i][3]
        for n, (d, (prev, close)) in enumerate(zip(days, _walk(i, drift, len(days)))):
            vol = 2_000_000 * (3.5 if sym == "SBIN" and n == len(days) - 1 else 1)
            rows.append((d, sym, "NSE", "EQ", prev, close * 1.01, close * 0.99, close, prev, vol, close * vol, 50_000))
            last[sym] = close
    now_rows, usd = [], 83.0
    for n, d in enumerate(days):   # ServiceNow, the RSU stock, in dollars
        close = 800 + n * 0.5 + (n % 7) * 3
        now_rows.append((d, "NOW", "NYSE", "EQ", close, close, close, close, close, 1_000_000, close * 1e6, 1000))
        db.execute("insert into fx values (?, 'USDINR', ?)", [d, usd + n * 0.004])
    insert_prices(db, rows + now_rows)
    for sym, name, industry, _d, pe, roe in STOCKS:
        db.execute("insert into stocks values (?, ?, ?, ?)", [sym, name, industry, "INE" + sym[:6].ljust(6, "0") + "01"])
        for metric, value in {"pe": pe, "pb": pe / 5, "roe": roe, "roce": roe * 1.2, "debt_to_equity": 0.3,
                              "profit_cagr_3y": 0.12 + roe / 5}.items():
            db.execute("insert into fundamentals values (?, ?, ?, ?, 'yahoo')", [AS_OF, sym, metric, value])
    db.execute("insert into surveillance values (?, 'ASMCO', 'ASM stage 2')", [AS_OF])
    for n, d in enumerate(_business_days(AS_OF, 400)):
        db.execute("insert into index_levels values (?, 'Nifty 50', ?, ?, 3.4, 1.3)", [d, 19000 + n * 18, 18 + (n % 90) / 15])
    db.execute("insert into holidays values ('2026-11-25', 'Guru Nanak Jayanti'), ('2026-12-25', 'Christmas')")
    for sym in WATCH:
        db.execute("insert into watchlist (symbol, exchange, added_by) values (?, 'NSE', 'import')", [sym])
    for sym in ("TCS", "ITC", "HDFCBANK"):   # imports also carry the BSE line of the same company
        db.execute("insert into watchlist (symbol, exchange, added_by) values (?, 'BSE', 'import')", [sym])
    for at, sym, text in [
            (datetime(2026, 11, 19, 17), "SBIN", "Dividend of Rs 13 per share, record date 28 Nov"),
            (datetime(2026, 11, 18, 17), "WIPRO", "Board meeting on 5 Dec to consider financial results"),
            (datetime(2026, 11, 19, 16), "ITC", "Board meeting on 2 Dec to consider financial results"),
            (datetime(2026, 11, 17, 12), "AXISBANK", "Bonus issue 1:1 announced; record date 4 Dec"),
            (datetime(2026, 11, 16, 12), "COALINDIA", "Interim dividend Rs 10.25 per share")]:
        db.execute("insert into announcements values (?, ?, ?, '', '')", [at, sym, text])

    snap = datetime(2026, 11, 20, 18, 0)
    gain = {"INFY": 0.12, "WIPRO": -0.08, "TATAMOTORS": -0.15, "HDFCBANK": 0.09, "ITC": 0.21, "RELIANCE": 0.04, "LT": 0.17,
            "BHARTIARTL": 0.3, "TATASTEEL": -0.04, "MARUTI": 0.11, "NTPC": 0.25, "COALINDIA": 0.06, "BAJFINANCE": -0.02,
            "TITAN": 0.14, "CIPLA": 0.08}
    worth = {"INFY": 330000, "WIPRO": 150000, "TATAMOTORS": 140000, "HDFCBANK": 400000, "ITC": 230000, "RELIANCE": 360000,
             "LT": 260000, "BHARTIARTL": 220000, "TATASTEEL": 120000, "MARUTI": 180000, "NTPC": 160000, "COALINDIA": 110000,
             "BAJFINANCE": 200000, "TITAN": 170000, "CIPLA": 90000}
    qty = {s: max(1, round(worth[s] / last[s])) for s in HELD}
    avg = {s: round(last[s] / (1 + gain[s]), 2) for s in HELD}
    for sym in HELD:
        isin = "INE" + sym[:6].ljust(6, "0") + "01"
        if sym == "HDFCBANK":   # the broker reports one holding in two rows; the page must show one
            half = qty[sym] // 2
            for q in (half, qty[sym] - half):
                db.execute("insert into holdings values (?, 'equity', ?, ?, ?, ?, 'kite')", [snap, sym, isin, q, avg[sym]])
        else:
            db.execute("insert into holdings values (?, 'equity', ?, ?, ?, ?, 'kite')", [snap, sym, isin, qty[sym], avg[sym]])
    funds = [(100001, "INF879O01027", "Parag Parikh Flexi Cap Fund", "Equity Scheme - Flexi Cap Fund", 5200, 68.0, 80.5),
             (100002, "INF789F01XA8", "UTI Nifty 50 Index Fund", "Equity Scheme - Index Fund", 2400, 140.0, 168.0),
             (100003, "INF179K01XQ0", "HDFC Short Term Debt Fund", "Debt Scheme - Short Duration Fund", 9000, 29.0, 31.4),
             (100004, "INF204KB14I2", "Nippon India Gold Savings Fund", "Other Scheme - Gold", 15000, 24.0, 33.1)]
    for code, isin, name, cat, units, cost, nav in funds:
        db.execute("insert into funds values (?, ?, '', ?, 'Direct', 'Growth', ?, '')", [code, isin, name, cat])
        for d in days[-30:]:
            db.execute("insert into navs values (?, ?, ?)", [d, code, nav])
        db.execute("insert into holdings values (?, 'mf', ?, ?, ?, ?, 'kite')", [snap, name, isin, units, cost])
    db.execute("insert into holdings values (?, 'rsu', 'NOW', 'US81762P1021', 12, 640, 'fidelity')", [snap])
    lot_dates = [date(2024, 5, 9), date(2025, 1, 20), date(2025, 6, 3), date(2025, 12, 5), date(2026, 3, 11), date(2026, 8, 1)]
    for k, sym in enumerate(HELD):
        if sym == "WIPRO":
            plan = [(200, date(2025, 10, 1)), (100, date(2025, 12, 1))]   # 100 shares turn long-term on 2 Dec 2026
        elif sym == "INFY":
            plan = [(qty[sym] * 6 // 10, date(2025, 12, 5)), (qty[sym] - qty[sym] * 6 // 10, date(2026, 8, 1))]
        else:
            plan = [(qty[sym], lot_dates[k % len(lot_dates)])]
        for q, acquired in plan:
            db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, source) values "
                       "('stock', ?, ?, ?, ?, ?, 'tradebook')",
                       [sym, "INE" + sym[:6].ljust(6, "0") + "01", acquired, q, avg[sym]])
    db.execute("update holdings set quantity = 300 where symbol = 'WIPRO'")
    db.execute("insert into runs (job, started_at, finished_at, status, notes) values "
               "('daily_decide', ?, ?, 'ok', ?)", [datetime(2026, 11, 20, 19, 0), datetime(2026, 11, 20, 19, 9),
               json.dumps({"calls": 30, "market_view": "Markets are steady. Banks lead, IT is mixed."})])
    db.execute("insert into runs (job, started_at, finished_at, status, notes) values "
               "('weekly', ?, ?, 'ok', '{}')", [datetime(2026, 11, 14, 10, 0), datetime(2026, 11, 14, 11, 0)])
    db.execute("insert into runs (job, started_at, finished_at, status, notes) values "
               "('nav', ?, ?, 'failed', ?)", [datetime(2026, 11, 19, 23, 30), datetime(2026, 11, 19, 23, 31),
               json.dumps({"error": "AMFI timed out"})])
    db.execute("insert into problems (job, severity, message, issue_url) values "
               "('nav', 'error', 'AMFI NAV file timed out; used yesterday''s NAVs', 'https://github.com/x/stockpilot/pull/7')")
    db.execute("insert into requests (kind, payload, status, applied_at) values "
               "('watchlist_add', '{\"symbol\": \"CIPLA\", \"exchange\": \"NSE\"}', 'done', ?)", [datetime(2026, 11, 19, 8, 0)])
    db.execute("insert into requests (kind, payload, status) values ('budget_set', '{\"month\": \"2026-12\", \"amount\": 150000}', 'pending')")

    def call(day, sym, kind, action, p, base, entry, stop, target, size, q, tax=None, skeptic=None, s=(None, None, None),
             why="", news=()):
        db.execute("""insert into calls (made_on, symbol, kind, action, probability, base_rate, horizon_days, entry, stop, target,
                      size_inr, reasons, risks, news, runner, skeptic, unproven, score_1m, score_3m, score_6m)
                      values (?, ?, ?, ?, ?, ?, 91, ?, ?, ?, ?, ?, ?, ?, 'claude', ?, true, ?, ?, ?)""",
                   [day, sym, kind, action, p, base, entry, stop, target, size,
                    json.dumps({"summary": why or f"{sym}: {action} call.", "moved_by": [{"reason": "Strong results", "points": 6},
                                {"reason": "Sector weak", "points": -3}], "sized_by": "budget", "quantity": q, "tax_note": tax}),
                    json.dumps(["Weak rupee could hurt margins"]), json.dumps(list(news)),
                    json.dumps(skeptic) if skeptic else None, *s])
    d = AS_OF
    px = lambda sym: round(last[sym], 2)   # noqa: E731
    call(d, "ICICIBANK", "candidate", "buy", 0.68, 0.55, px("ICICIBANK"), round(px("ICICIBANK") * .94), round(px("ICICIBANK") * 1.14),
         40000, 36, why="Earnings keep growing and the stock sits above both averages. Banks lead the market.")
    call(d, "M&M", "candidate", "buy", 0.64, 0.53, px("M&M"), round(px("M&M") * .93), round(px("M&M") * 1.15), 30000, 9,
         skeptic={"probability": 0.62, "summary": "Valuation is full; wait for a dip."},
         why="Tractor and SUV demand are both rising. Profit growth beats the sector.")
    call(d, "SUNPHARMA", "candidate", "buy", 0.61, 0.52, px("SUNPHARMA"), round(px("SUNPHARMA") * .94),
         round(px("SUNPHARMA") * 1.12), 20000, 12, why="Pharma is turning up and you hold no pharma beyond Cipla.")
    call(d, "WIPRO", "holding", "sell", 0.33, 0.45, px("WIPRO"), round(px("WIPRO") * .95), round(px("WIPRO") * 1.02), 0, 300,
         tax="100 shares turn long-term on 2026-12-02 (12 days). Waiting cuts tax from 20% to 12.5%.",
         why="It trails every other IT stock and the results on 5 Dec look weak. Sell the 200 long-term shares now; hold the other 100 until 2 Dec.")
    for sym in HELD:
        if sym != "WIPRO":
            call(d, sym, "holding", "hold", 0.5 + (_h(sym) % 7) / 100, 0.5, px(sym), round(px(sym) * .92), round(px(sym) * 1.12), 0, 0,
                 why="No reason to act. Trend and earnings are intact.")
    for sym in ["SBIN", "TCS", "AXISBANK", "HINDUNILVR", "DRREDDY", "HCLTECH", "KOTAKBANK", "NESTLEIND", "ASIANPAINT",
                "ULTRACEMCO", "JSWSTEEL", "TVSMOTOR"]:
        call(d, sym, "candidate", "watch", 0.5 + (_h(sym) % 8) / 100, 0.5, px(sym), round(px(sym) * .93), round(px(sym) * 1.1), 0, 0,
             why="Good company, but the price is not attractive yet.", news=["SBIN-1"] if sym == "SBIN" else [])
    rng = random.Random(7)
    names = [x[0] for x in STOCKS]
    for n in range(45):  # older, scored calls
        p = rng.choice([0.45, 0.55, 0.65, 0.7])
        hit = rng.random() < p - 0.05
        score = lambda: round(rng.uniform(0.01, 0.12) * (1 if hit else -1), 4)
        call(AS_OF - timedelta(days=100 + n * 3), names[n % 13], "candidate", "buy" if p > 0.6 else "watch",
             p, 0.5, 100, 90, 120, 10000, 10, s=(score(), score(), score() if n % 2 else None))
    # what the weekly job stores (weekly_reports) and the config gives the site; the site reshapes both for the Portfolio and Health tabs
    target = {"stocks": 0.6, "equity_funds": 0.2, "gold": 0.1, "debt_funds": 0.1}
    db.execute("insert into target_allocations (allocation, approved_by) values (?, 'papa')", [json.dumps({"target": target})])
    pool = lambda total: {k: (total if i == 0 else 0) for i, k in enumerate((*tax.SHORT_POOLS, *tax.LONG_POOLS))}
    for section, payload in {
        "allocation": {"as_of": str(AS_OF), "rows": [{"class": k, "target": v} for k, v in
                                                     {"stocks": 0.55, "equity_funds": 0.25, "gold": 0.1, "debt_funds": 0.1}.items()]},
        "funds": {"as_of": str(AS_OF), "funds": [
            {"name": "Parag Parikh Flexi Cap Fund", "verdict": "hold", "why": "Beats most peers over 3 years; cost is low."},
            {"name": "HDFC Short Term Debt Fund", "verdict": "hold", "why": "Steady, low cost, does its job as the safe part."}]},
        "opportunities": {"as_of": str(AS_OF), "picks": [
            {"symbol": "Gold ETF", "why": "You hold no gold. A 10% share would steady the portfolio."}]},
        "tax": {"as_of": str(AS_OF), "fy": "2026-27", **pool(84000), "harvest": {"gain_room": 42000, "gain_candidates": [], "loss_candidates": []},
                "warnings": ["Loss harvesting could save about ₹5,250 in tax."], "expected_vests": [], "schedule_fa": ["ServiceNow", "ServiceNow RSU"]},
    }.items():
        db.execute("insert into weekly_reports values (?, ?, ?)", [AS_OF, section, json.dumps(payload)])
    return db
