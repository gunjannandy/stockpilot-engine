"""Capture today's Python money outputs as fixtures for the TypeScript port (decisions §3).

    cd py && uv run --frozen python ../tools/capture/capture.py

Builds each scenario in a throwaway DuckDB store, runs the real Python money code on it and saves the
scenario's inputs and outputs, as JSON, under money/captured/. Nothing here reads the vault: every row is
made up. The TypeScript checks replay each input and require the output to match exactly. Run it again
only to add a scenario; `--check` fails when a saved file would change (the Python is the reference).
"""
import json
import random
import sys
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "py"))
sys.path.insert(0, str(ROOT / "py" / "tests"))

from helpers import insert_prices  # noqa: E402
from stockpilot import store  # noqa: E402
from stockpilot.book import positions, record, units  # noqa: E402
from stockpilot.trades import corporate_actions, lots  # noqa: E402
from stockpilot.trades.lots import Trade  # noqa: E402

OUT = ROOT / "money" / "captured"
KITE_AT = datetime(2026, 11, 20, 9)


def _day(d):
    return None if d is None else str(d)


def new_db():
    return store.open(Path(tempfile.mkdtemp()) / "t.duckdb")


# ---------------------------------------------------------------------------------------------- lots

def trade_json(t: Trade):
    return {"source": t.source, "sourceRef": t.source_ref, "kind": t.kind, "symbol": t.symbol, "isin": t.isin,
            "side": t.side, "tradeDate": str(t.trade_date), "quantity": t.quantity, "price": t.price,
            "currency": t.currency, "status": t.status, "tradeKey": t.trade_key}


def action_json(a):
    return {"symbol": a.symbol, "isin": a.isin, "exDate": str(a.ex_date), "kind": a.kind, "numerator": a.numerator,
            "denominator": a.denominator, "newIsin": a.new_isin, "newSymbol": a.new_symbol,
            "costFraction": a.cost_fraction, "price": a.price, "source": a.source}


def lots_case(name, trades, actions=(), stocks=None, kite=None, duplicates=False):
    """Run lots.save_trades + corporate_actions.save + lots.rebuild on a fresh store."""
    db = new_db()
    for sym, isin in (stocks or {}).items():
        db.execute("insert into stocks (symbol, name, isin) values (?, ?, ?)", [sym, sym, isin])
    if kite:
        for kind, symbol, isin, qty, avg in kite:
            db.execute("insert into holdings values (?, ?, ?, ?, ?, ?, 'kite')", [KITE_AT, kind, symbol, isin, qty, avg])
    saved = lots.save_trades(db, trades)
    corporate_actions.save(db, list(actions))
    result = lots.rebuild(db)
    stored = db.execute("select kind, symbol, isin, acquired_on, quantity, cost_per_unit, currency, closed_quantity, "
                        "source, source_ref, estimated from lots order by id").fetchall()
    sales = db.execute("select kind, symbol, isin, sold_on, quantity, price_per_unit, currency, source, source_ref "
                       "from sales order by id").fetchall()
    held = lots.holdings(db)
    return {
        "name": name,
        "input": {"trades": [trade_json(t) for t in trades], "actions": [action_json(a) for a in actions],
                  "stocks": stocks or {},
                  "kite": {"at": str(KITE_AT.date()), "rows": [{"kind": k, "symbol": s, "isin": i, "quantity": q,
                                                                "avgPrice": a} for k, s, i, q, a in kite]} if kite else None},
        "output": {
            "saved": saved,
            "lots": [{"kind": k, "symbol": s, "isin": i, "acquiredOn": _day(on), "quantity": q, "costPerUnit": c,
                      "currency": cur, "closedQuantity": cl, "source": src, "sourceRef": ref, "estimated": bool(est)}
                     for k, s, i, on, q, c, cur, cl, src, ref, est in stored],
            "sales": [{"kind": k, "symbol": s, "isin": i, "soldOn": _day(on), "quantity": q, "pricePerUnit": p,
                       "currency": cur, "source": src, "sourceRef": ref} for k, s, i, on, q, p, cur, src, ref in sales],
            "unmatchedSells": [[i, str(d), q] for i, d, q in result.unmatched_sells],
            "holdings": [{"kind": h.kind, "symbol": h.symbol, "isin": h.isin, "quantity": h.quantity,
                          "avgCost": h.avg_cost, "currency": h.currency} for h in held],
        },
    }


def T(symbol, isin, side, day, qty, price, source="contract_note", kind="stock", currency="INR", status="confirmed", key=None):
    return Trade(source, key or f"{symbol}{day}{side}{qty}", kind, symbol, isin, side, day, qty, price, currency, status, key)


REL, INFY = "INE002A01018", "INE009A01021"


def lots_cases():
    A = corporate_actions.Action
    out = []
    # the hand example from py/tests/trades/test_trades_lots.py
    out.append(lots_case("hand example: split, bonus, FIFO across both", [
        T("RELIANCE", REL, "buy", date(2023, 1, 10), 10, 50.0, key="r1"),
        T("RELIANCE", REL, "buy", date(2023, 3, 15), 10, 60.0, key="r2"),
        T("RELIANCE", REL, "sell", date(2023, 4, 5), 4, 90.0, key="r3"),
        T("RELIANCE", REL, "sell", date(2023, 6, 20), 16, 100.0, key="r4"),
        T("INFY", INFY, "buy", date(2023, 5, 2), 7, 1500.0, key="i1"),
        T("RELIANCE", REL, "buy", date(2024, 3, 1), 6, 70.0, key="r5"),
        T("RELIANCE", REL, "sell", date(2024, 4, 4), 6, 80.0, key="r6")],
        [A("RELIANCE", REL, date(2023, 9, 1), "split", 2, 1, "Split"),
         A("RELIANCE", REL, date(2024, 2, 1), "bonus", 1, 1, "Bonus 1:1")]))
    out.append(lots_case("a sell with no buy is reported, not invented", [
        T("TCS", "INE467B01029", "sell", date(2024, 1, 5), 4, 3500.0, source="tradebook", key="x1")]))
    out.append(lots_case("expected vests never become lots", [
        T("NOW", "US81762P1021", "vest", date(2026, 8, 15), 10, 800.0, source="fidelity", kind="rsu", currency="USD", key="v1"),
        T("NOW", "US81762P1021", "vest", date(2026, 11, 15), 10, None, source="rsu_inference", kind="rsu", currency="USD",
          status="expected", key="v2")]))
    out.append(lots_case("a split that changed the ISIN still matches old buys to new sells", [
        T("CANBK", "INE476A01014", "buy", date(2024, 1, 2), 100, 500.0, key="c1"),
        T("CANBK", "INE476A01022", "sell", date(2024, 9, 5), 445, 105.0, key="c2")],
        [A("CANBK", "INE476A01014", date(2024, 5, 15), "split", 5, 1, "Split")]))
    out.append(lots_case("a series suffix on the symbol does not hide a bonus", [
        T("NBCC-A", "INE095N01031", "buy", date(2024, 1, 2), 100, 150.0, key="n1")],
        [A("NBCC", "INE095N01015", date(2024, 10, 7), "bonus", 1, 2, "Bonus")]))
    out.append(lots_case("lots bought before an ISIN change carry the current ISIN", [
        T("CESC", "INE486A01013", "buy", date(2020, 1, 2), 20, 600.0, key="e1")], stocks={"CESC": "INE486A01021"}))
    out.append(lots_case("a renamed company and a spaced series suffix are one holding", [
        T("TWL", "INE615H01020", "buy", date(2023, 6, 16), 41, 424.0, key="t1"),
        T("TITAGARH", "INE615H01020", "sell", date(2023, 9, 15), 41, 764.0, key="t2"),
        T("JSL", "INE220G01021", "buy", date(2022, 5, 6), 50, 164.0, key="j1"),
        T("JSL - A", "INE220G01021", "buy", date(2022, 5, 27), 100, 117.0, key="j2")]))
    out.append(lots_case("the same trade from two sources counts once", [
        T("TCS", "INE467B01029", "buy", date(2024, 1, 5), 4, 3500.0, source="tradebook"),
        T("TCS", "INE467B01029", "buy", date(2024, 1, 5), 4, 3500.0, source="contract_note")]))
    out.append(lots_case("a demerger hands cost and units to the new company", [
        T("VEDL", "INE205A01025", "buy", date(2024, 1, 2), 100, 400.0, key="d1"),
        T("VEDL", "INE205A01025", "buy", date(2025, 6, 2), 50, 300.0, key="d2"),
        T("VEDL", "INE205A01025", "sell", date(2026, 5, 4), 30, 350.0, key="d3"),
        T("VEDLNEW", "INE0NEW01011", "sell", date(2026, 6, 4), 20, 90.0, key="d4")],
        [A("VEDL", "INE205A01025", date(2026, 4, 30), "demerger", 1, 1, "Demerger", "owner", "INE0NEW01011", "VEDLNEW", 0.3)]))
    out.append(lots_case("a demerger without its ratio changes nothing", [
        T("VEDL", "INE205A01025", "buy", date(2024, 1, 2), 100, 400.0, key="d1")],
        [A("VEDL", "INE205A01025", date(2026, 4, 30), "demerger", 1, 1, "Demerger")]))
    out.append(lots_case("rights: taken up by the owner count, NSE's bare notice does not", [
        T("BASML", "INE186H01022", "buy", date(2024, 1, 2), 100, 60.0, key="b1"),
        T("OTHER", "INE000O01011", "buy", date(2024, 1, 2), 80, 20.0, key="o1")],
        [A("BASML", "INE186H01022", date(2024, 8, 1), "rights", 1, 4, "Rights", "owner", None, None, None, 55.0),
         A("OTHER", "INE000O01011", date(2024, 8, 1), "rights", 1, 4, "Rights", "nse", None, None, None, 55.0)]))
    out.append(lots_case("a mutual fund is keyed by its ISIN", [
        T("PPFAS FLEXI", "INF879O01027", "buy", date(2025, 4, 2), 234.962, 85.1159, source="tradebook", kind="mf",
          key="mf:2025-04-02:INF879O01027:buy:234.962"),
        T("PPFAS FLEXI DIRECT", "INF879O01027", "buy", date(2025, 7, 1), 215.789, 92.6786, source="tradebook", kind="mf",
          key="mf:2025-07-01:INF879O01027:buy:215.789"),
        T("PPFAS FLEXI", "INF879O01027", "sell", date(2025, 9, 1), 100.5, 99.0, source="coin", kind="mf", key="mf:sell1")]))
    out.append(lots_case("a key made from the trade itself, with fractional and large amounts", [
        T("TCS", "INE467B01029", "buy", date(2024, 1, 5), 4.5, 3500.0),
        T("TCS", "INE467B01029", "buy", date(2024, 1, 5), 1234567.0, 12.5),
        T("TCS", "INE467B01029", "buy", date(2024, 1, 5), 0.00001234, 0.1)]))
    kite = [("stock", "TCS", "INE467B01029", 12, 3100.0), ("stock", "NEWIPO", "INE000N01011", 50, 140.0),
            ("mf", "INF879O01027", "INF879O01027", 7162.094, 70.0), ("stock", "INFY", INFY, 7, 1500.0)]
    out.append(lots_case("units Kite shows that no document explains become one estimated lot", [
        T("TCS", "INE467B01029", "buy", date(2025, 1, 10), 10, 3000.0, key="k1"),
        T("INFY", INFY, "buy", date(2025, 2, 10), 7, 1500.0, key="k2"),
        T("PARAG", "INF879O01027", "buy", date(2024, 1, 5), 4890.044, 60.0, kind="mf", key="k3"),
        T("NOW", "US81762P1021", "vest", date(2026, 2, 9), 6, 100.0, kind="rsu", currency="USD", key="k4")], kite=kite))
    return out + random_lots_cases()


def random_lots_cases(n=120, seed=20261127):
    """Seeded random histories: buys, sells (some too big), splits, bonuses, demergers, rights, renames, series suffixes."""
    rng = random.Random(seed)
    A = corporate_actions.Action
    cases = []
    for c in range(n):
        trades, actions, kite = [], [], []
        names = [(f"S{c}A", f"INE{c:03d}A01011"), (f"S{c}B", f"INE{c:03d}B01012"), (f"S{c}C-A", f"INE{c:03d}C01013")]
        stocks = {}
        for sym, isin in names[: rng.randint(1, 3)]:
            base = sym.split("-")[0]
            day = date(2022, 1, 1) + timedelta(days=rng.randint(0, 300))
            for _ in range(rng.randint(1, 8)):
                day += timedelta(days=rng.randint(0, 120))
                side = "sell" if rng.random() < 0.35 else "buy"
                label = base + (" - A" if rng.random() < 0.15 else "")
                qty = rng.choice([1, 2, 5, 10, 25, 100, 0.5, 3.25, 17.125, 250])
                price = round(rng.uniform(5, 3000), rng.choice([0, 1, 2, 4]))
                trades.append(T(label, isin, side, day, qty, price, key=f"{sym}{len(trades)}"))
            if rng.random() < 0.7:
                for _ in range(rng.randint(1, 2)):
                    ex = date(2022, 6, 1) + timedelta(days=rng.randint(0, 900))
                    kind = rng.choice(["split", "bonus", "demerger", "rights", "rights"])
                    num, den = rng.choice([(2, 1), (5, 1), (10, 1), (1, 1), (1, 2), (3, 2), (1, 4)])
                    if kind == "demerger":
                        actions.append(A(base, isin, ex, "demerger", num, den, "d", "owner", f"INE{c:03d}Z01019", f"S{c}NEW",
                                         rng.choice([0.1, 0.25, 0.4, 0.7])))
                        if rng.random() < 0.6:
                            trades.append(T(f"S{c}NEW", f"INE{c:03d}Z01019", "sell", ex + timedelta(days=rng.randint(1, 200)),
                                            rng.choice([1, 2, 5, 40]), rng.choice([10.0, 55.5, 120.0]), key=f"new{len(trades)}"))
                    elif kind == "rights":
                        actions.append(A(base, isin, ex, "rights", num, den, "r", rng.choice(["owner", "owner", "nse"]),
                                         None, None, None, round(rng.uniform(10, 500), 2)))
                    else:
                        actions.append(A(base, isin, ex, kind, num, den, kind))
            if rng.random() < 0.15:
                stocks[base] = isin[:-1] + "9"
        if rng.random() < 0.3:
            for sym, isin in names[:2]:
                kite.append(("stock", sym.split("-")[0], isin, rng.choice([1, 5, 20, 120.5]), rng.choice([100.0, 250.5, 1400.0])))
        cases.append(lots_case(f"random {c}", trades, actions, stocks, kite or None))
    return cases



# ---------------------------------------------------------------------------------------------- rounding

def rounding_cases(seed=7):
    rng = random.Random(seed)
    xs = [0.5, 1.5, 2.5, -0.5, -1.5, 0.125, 0.375, 1 / 128, 0.0078125, 0.0000005, 2.675, 1.005, 100.0, 1e-7, 123456.789,
          0.1 + 0.2, 33.333333333, 66.66666666666667, 0.045, 2.345, 1234567.0000005, 0.285, 1.115, 1e15 + 0.5]
    xs += [rng.uniform(-1000, 1000) for _ in range(150)] + [round(rng.uniform(0, 50), 3) / 8 for _ in range(60)]
    xs += [rng.randint(-2000, 2000) / 2 ** rng.randint(1, 9) for _ in range(120)]
    out = {"round": [], "floordiv": [], "int": [], "sum": [], "fixed": []}
    for x in xs:
        for n in (0, 1, 2, 3, 6):
            out["round"].append([x, n, round(x, n)])
        out["int"].append([x, int(x)])
        for y in (1.0, 2.0, 0.3, 7.0, -3.0):
            out["floordiv"].append([x, y, x // y])
        for n in (0, 2):
            out["fixed"].append([x, n, f"{x:.{n}f}"])
    for _ in range(80):
        vals = [rng.choice([0.1, 0.2, 0.3, 1e16, 1.0, -1e16, 1 / 3, rng.uniform(-5, 5), 1e-9]) for _ in range(rng.randint(0, 12))]
        out["sum"].append([vals, sum(vals)])
    out["sum"].append([[0.1] * 10, sum([0.1] * 10)])
    return out


# ---------------------------------------------------------------------------------------------- positions, units, dust

class Recorder:
    """Wraps valuation.unit_prices_inr so a case saves the price it gave each item."""

    def __init__(self):
        from stockpilot import valuation
        self.valuation, self.orig, self.seen = valuation, valuation.unit_prices_inr, {}

    def __enter__(self):
        def wrapped(db, items, as_of, fund_codes=None, rate=None):
            prices = self.orig(db, items, as_of, fund_codes, rate)
            for i, p in zip(items, prices):
                self.seen[f"{i['kind']}|{i['symbol']}|{i['isin']}"] = p
            return prices
        self.valuation.unit_prices_inr = wrapped
        return self

    def __exit__(self, *a):
        self.valuation.unit_prices_inr = self.orig


def seed_world(db, stocks=(), funds=(), prices=(), fx_rows=(), navs=()):
    for s in stocks:
        db.execute("insert into stocks values (?, ?, 'Misc', ?)", list(s))
    for f in funds:
        db.execute("insert into funds values (?, ?, null, ?, 'Direct', 'Growth', ?, '')", list(f))
    if prices:
        insert_prices(db, [(d, sym, ex, "EQ", 0, 0, 0, close, 0, 0, 0, 0) for d, sym, ex, close in prices])
    for d, r in fx_rows:
        db.execute("insert into fx values (?, 'USDINR', ?)", [d, r])
    for d, code, nav in navs:
        db.execute("insert into navs values (?, ?, ?)", [d, code, nav])


def add_lot(db, kind, symbol, isin, on, qty, cost, currency="INR", closed=0, estimated=False):
    db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, currency, closed_quantity, "
               "source, estimated) values (?, ?, ?, ?, ?, ?, ?, ?, 'trades:test', ?)",
               [kind, symbol, isin, on, qty, cost, currency, closed, estimated])


def add_kite(db, kind, symbol, isin, qty, avg):
    db.execute("insert into holdings values (?, ?, ?, ?, ?, ?, 'kite')", [KITE_AT, kind, symbol, isin, qty, avg])


def world_json(db):
    """Everything `held` and `gaps` read, as the TypeScript takes it."""
    lot_rows = db.execute("select kind, symbol, isin, acquired_on, quantity, closed_quantity, cost_per_unit, currency, "
                          "estimated from lots order by acquired_on, id").fetchall()
    snap = positions.last_kite_sync(db)
    kite = {"at": str(snap.date()), "rows": [
        {"kind": k, "symbol": s, "isin": i, "quantity": q, "avgPrice": a} for k, s, i, q, a in db.execute(
            "select kind, symbol, isin, quantity, avg_price from holdings where snapshot_at = ?", [snap]).fetchall()]} if snap else None
    as_of = db.execute("select max(as_of) from holding_statements").fetchone()[0]
    statement = dict(db.execute("select isin, quantity from holding_statements where as_of = ? and quantity > 0",
                                [as_of]).fetchall()) if as_of else {}
    def lot_json(rows):
        return [{"kind": k, "symbol": s, "isin": i, "acquiredOn": str(on), "quantity": q, "closedQuantity": cl,
                 "costPerUnit": c, "currency": cur, "estimated": bool(est)} for k, s, i, on, q, cl, c, cur, est in rows]
    by_id = db.execute("select kind, symbol, isin, acquired_on, quantity, closed_quantity, cost_per_unit, currency, "
                       "estimated from lots order by id").fetchall()
    return {
        "lots": lot_json(lot_rows),
        "lotsById": lot_json(by_id),   # the table's own order: the unit check sums in it
        "stocks": [{"symbol": s, "name": n, "isin": i} for s, n, i in db.execute("select symbol, name, isin from stocks").fetchall()],
        "funds": [{"schemeCode": c, "name": n, "plan": p, "option": o, "category": cat, "isinGrowth": g, "isinReinvest": r}
                  for c, g, r, n, p, o, cat in db.execute(
                      "select scheme_code, isin_growth, isin_reinvest, name, plan, option, category from funds").fetchall()],
        "kite": kite, "statement": statement,
        "fx": [[str(d), r] for d, r in db.execute("select date, rate from fx where pair = 'USDINR' order by date").fetchall()],
    }


def position_json(p):
    return {"kind": p.kind, "symbol": p.symbol, "isin": p.isin, "name": p.name, "quantity": p.quantity,
            "avgCost": p.avg_cost, "price": p.price, "source": p.source, "check": p.check, "value": p.value,
            "lots": [{"acquiredOn": str(l.acquired_on), "quantity": l.quantity, "cost": l.cost,
                      "turnsLongTermOn": _day(l.turns_long_term_on)} for l in p.lots]}


def positions_case(name, build, as_of):
    db = new_db()
    build(db)
    world = world_json(db)
    from stockpilot.book import kinds, positions as pos
    from stockpilot.analysis import tax
    funds = pos._funds_by_isin(db)
    rules = [{"kind": l["kind"], "isin": l["isin"], "currency": l["currency"], "acquiredOn": l["acquiredOn"],
              "day": _day(tax.turns_long_term_on(pos._bucket(funds, l["kind"], l["isin"], l["currency"] or "INR",
                                                             date.fromisoformat(l["acquiredOn"])),
                                                 date.fromisoformat(l["acquiredOn"])))} for l in world["lots"]]
    with Recorder() as rec:
        got = pos.held(db, as_of)
    gaps = units.gaps(db)
    return {"name": name, "asOf": str(as_of), "input": {**world, "turnsLongTermOn": rules, "prices": rec.seen},
            "output": {"positions": [position_json(p) for p in got],
                       "gaps": [{"isin": g.isin, "symbol": g.symbol, "kite": g.kite, "lots": g.lots, "message": g.message} for g in gaps],
                       "findings": units.findings(db)}}


DAY = date(2026, 11, 20)
PPFAS, OTHER_FUND = "INF879O01027", "INF732E01037"
BASE_STOCKS = [("TCS", "Tata Consultancy Services", "INE467B01029"), ("NEWIPO", "New Listing Ltd", "INE000N01011"),
               ("NIFTYBEES", "Nippon India ETF Nifty BeES", "INF204KB17I5"), ("ABREL", "Aditya Birla Real Estate", "INE055A01016")]
BASE_FUNDS = [(1, PPFAS, "Parag Parikh Flexi Cap Fund", "Equity Scheme - Flexi Cap Fund"),
              (2, OTHER_FUND, "Some Other Fund", "Debt Scheme - Liquid Fund"),
              (3, "INF204KB17I5", "Nippon ETF", "Other"),
              (4, "INF000G01011", "Gold Savings Fund", "Other Scheme - Gold ETF"),
              (5, "INF000H01011", "Aggressive Hybrid Fund", "Hybrid Scheme - Aggressive Hybrid Fund")]
BASE_PRICES = [(DAY, "TCS", "NSE", 4000.0), (DAY, "TCS", "BSE", 3999.0), (DAY, "NEWIPO", "NSE", 150.0),
               (DAY, "NOW", "NYSE", 1000.0), (DAY, "NIFTYBEES", "NSE", 260.0), (DAY, "ABREL", "BSE", 2000.0)]


def world(db, prices=BASE_PRICES):
    seed_world(db, BASE_STOCKS, BASE_FUNDS, prices, [(DAY, 85.0), (date(2025, 3, 1), 86.5)],
               [(DAY, 1, 75.0), (DAY, 2, 1050.0), (DAY, 4, 60.0), (DAY, 5, 31.0)])


def positions_cases():
    out = []
    TCS = "INE467B01029"

    def a(db):
        world(db)
        add_lot(db, "stock", "TCS", TCS, date(2025, 1, 10), 10, 3000.0)
        add_lot(db, "stock", "TCS", TCS, date(2026, 6, 1), 20, 3600.0, closed=10)
    out.append(positions_case("no Kite login: the lots are the holdings", a, DAY))

    def b(db):
        world(db)
        add_kite(db, "stock", "NEWIPO", "INE000N01011", 50, 140.0)
    out.append(positions_case("a Kite holding with no lots still shows", b, DAY))

    def c(db):
        world(db)
        add_lot(db, "stock", "TCS", TCS, date(2025, 1, 10), 10, 3000.0)
        add_kite(db, "stock", "TCS", TCS, 12, 3100.0)
    out.append(positions_case("Kite decides the units and the gap is named", c, DAY))

    def d(db):
        world(db)
        db.execute("insert into holding_statements values ('2026-10-31', 'INE000N01011', 50)")
    out.append(positions_case("the depository statement fills a gap", d, DAY))

    def e(db):
        world(db)
        add_lot(db, "rsu", "NOW", "US81762P1021", date(2025, 3, 1), 4, 800.0, currency="USD")
    out.append(positions_case("foreign shares priced and costed in rupees", e, DAY))

    def f(db):
        world(db)
        add_lot(db, "stock", "ABREL", "INE055A01016", date(2023, 5, 2), 8, 900.0)
        add_lot(db, "stock", "CENTURYTEX", "INE055A01016", date(2023, 5, 2), 8, 900.0)
        add_kite(db, "stock", "ABREL-BE", "INE055A01016", 16, 900.0)
    out.append(positions_case("a renamed company shows under its current NSE symbol", f, DAY))

    def g(db):
        world(db)
        add_lot(db, "stock", "NIFTYBEES", "INF204KB17I5", date(2024, 1, 5), 100, 230.0)
        add_lot(db, "mf", "PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN", PPFAS, date(2024, 1, 5), 50, 60.0)
        add_lot(db, "mf", "GOLD", "INF000G01011", date(2024, 1, 5), 10, 50.0)
        add_lot(db, "mf", "HYB", "INF000H01011", date(2024, 1, 5), 10, 30.0)
    out.append(positions_case("an ETF keeps its symbol, a fund its name, tax buckets by category", g, DAY))

    def h(db):
        world(db)
        add_lot(db, "stock", "TCS", TCS, date(2024, 1, 10), 10, 3000.0)
        add_lot(db, "stock", "TCS", TCS, date(2026, 6, 1), 20, 3600.0)
        add_kite(db, "stock", "TCS", TCS, 20, 3600.0)
        add_kite(db, "stock", "OTHER", "INE000X01011", 5, 10.0)
    out.append(positions_case("documents show more than Kite: trimmed oldest first", h, DAY))

    def i(db):
        world(db)
        add_kite(db, "stock", "TCS", TCS, 1, 3000.0)
        db.execute("insert into holding_statements values ('2026-10-31', ?, 0.195)", [OTHER_FUND])
        db.execute("insert into holding_statements values ('2026-10-31', 'INF204KB17I5', 50), ('2026-10-31', 'INE000Z01019', 7)")
    out.append(positions_case("a fund only the depository knows shows; a share or ETF stays hidden", i, DAY))

    def j(db):
        world(db)
        add_lot(db, "stock", "TCS", TCS, date(2025, 1, 10), 1, 3000.0)
    out += [positions_case("prices: NSE wins a tie", j, DAY), positions_case("prices: the latest close on or before the day", j, date(2026, 11, 25)),
            positions_case("prices: none stored before the first close", j, date(2026, 11, 1))]

    def k(db):
        world(db)
        add_lot(db, "stock", "TCS", TCS, date(2025, 1, 10), 10, 3000.0)
        add_lot(db, "mf", "PARAG", PPFAS, date(2024, 1, 5), 4890.044, 60.0)
        add_lot(db, "stock", "NEWIPO", "INE000N01011", date(2026, 2, 1), 12.5, 100.0, estimated=True)
        add_kite(db, "stock", "TCS", TCS, 12, 3100.0)
        add_kite(db, "mf", PPFAS, PPFAS, 7162.094, 70.0)
        add_kite(db, "stock", "NEWIPO", "INE000N01011", 12.5, 100.0)
        db.execute("insert into holding_statements values ('2026-10-31', ?, 0.195)", [OTHER_FUND])
    out.append(positions_case("Parag Parikh gap, estimated lot and a fund the depository alone knows", k, DAY))
    return out + random_positions_cases()


def random_positions_cases(n=90, seed=99):
    rng = random.Random(seed)
    cases = []
    for c in range(n):
        def build(db, rng=rng):
            stocks = [(f"Z{i}", f"Zed {i}", f"INE{i:03d}Z01011") for i in range(5)]
            funds = [(10 + i, f"INF{i:03d}Z01011", f"Fund {i}", rng.choice(
                ["Equity Scheme - Large Cap Fund", "Debt Scheme - Liquid Fund", "Hybrid Scheme - Balanced Hybrid Fund", "Other"]))
                for i in range(3)]
            prices = [(DAY - timedelta(days=rng.randint(0, 3)), s[0], rng.choice(["NSE", "BSE"]), round(rng.uniform(1, 900), 2))
                      for s in stocks if rng.random() < 0.85] + [(DAY, "NOW", "NYSE", 1000.0)]
            seed_world(db, stocks, funds, prices, [(DAY, round(rng.uniform(80, 90), 3)), (date(2025, 3, 1), 84.0)],
                       [(DAY, f[0], round(rng.uniform(10, 500), 3)) for f in funds if rng.random() < 0.8])
            idents = [("stock", s[0], s[2]) for s in stocks] + [("mf", f[1], f[1]) for f in funds]
            for kind, sym, isin in idents:
                if rng.random() < 0.7:
                    for _ in range(rng.randint(1, 4)):
                        qty = rng.choice([1, 3, 10, 25.5, 100, 7.125, 0.195])
                        add_lot(db, kind, sym, isin, date(2023, 1, 1) + timedelta(days=rng.randint(0, 1100)), qty,
                                round(rng.uniform(1, 800), 2), closed=rng.choice([0, 0, 0, qty / 2, qty]),
                                estimated=rng.random() < 0.1)
            if rng.random() < 0.4:
                add_lot(db, "rsu", "NOW", "US81762P1021", date(2025, 1, 1) + timedelta(days=rng.randint(0, 600)),
                        rng.choice([2, 4.5]), 800.0, currency="USD")
            if rng.random() < 0.6:
                for kind, sym, isin in idents:
                    if rng.random() < 0.6:
                        add_kite(db, kind, sym if kind == "stock" else isin, isin,
                                 rng.choice([0.195, 1, 5, 10, 24.5, 100, 7.125, 40]), round(rng.uniform(1, 800), 2))
            if rng.random() < 0.5:
                for kind, sym, isin in idents:
                    if rng.random() < 0.4:
                        db.execute("insert into holding_statements values ('2026-10-31', ?, ?)",
                                   [isin, rng.choice([0.195, 5, 10, 100])])
        cases.append(positions_case(f"random {c}", build, DAY))
    return cases


def dust_cases():
    out = []
    P = positions.Position
    rng = random.Random(5)
    for c in range(60):
        rows = []
        for i in range(rng.randint(1, 6)):
            qty = rng.choice([0.195, 1, 5, 10, 50])
            price = rng.choice([None, 1000.0, 999.99, 5000.0, 4000.0, 200.0, 0.0])
            avg = rng.choice([None, 300.0, 1500.0])
            src = rng.choice(["statement", "kite", "lots"])
            p = P("equity", f"S{i}", None, f"S{i}", qty, avg, None, src)
            p.price = price
            rows.append(p)
        kept = positions.without_dust(rows)
        out.append({"input": [{"symbol": p.symbol, "quantity": p.quantity, "avgCost": p.avg_cost, "price": p.price,
                               "source": p.source} for p in rows], "output": [p.symbol for p in kept]})
    return out


# ---------------------------------------------------------------------------------------------- own record, acted

def record_case(name, build, as_of):
    from stockpilot.book import pairs as pairing
    db = new_db()
    build(db)
    _, _, pairs = pairing.load(db)
    symbols = sorted({p["symbol"] for p in pairs})
    prices = pairing.prices_for(db, symbols, date(2000, 1, 1))
    nifty = pairing.nifty(db)
    body = record.build(db, as_of)
    return {"name": name, "input": {
        "asOf": str(as_of),
        "pairs": [{"route": p["route"], "symbol": p["symbol"], "acquiredOn": str(p["acquired_on"]), "soldOn": str(p["sold_on"]),
                   "quantity": p["quantity"], "cost": p["cost"], "proceeds": p["proceeds"], "gain": p["gain"]} for p in pairs],
        "prices": {s: [[str(d), v] for d, v in zip(ser.days, ser.values)] for s, ser in prices.items()},
        "nifty": [[str(d), v] for d, v in zip(nifty.days, nifty.values)]},
        "output": {"asOf": body["as_of"], "closed": body["closed"], "winners": body["winners"], "losers": body["losers"],
                   "winRate": body["win_rate"], "avgDaysWinners": body["avg_days_winners"],
                   "avgDaysLosers": body["avg_days_losers"],
                   "soldEarly": {"checked": body["sold_early"]["checked"], "roseAfter": body["sold_early"]["rose_after"],
                                 "share": body["sold_early"]["share"]},
                   "vsNifty": {"checked": body["vs_nifty"]["checked"], "beat": body["vs_nifty"]["beat"],
                               "share": body["vs_nifty"]["share"], "averageGapPoints": body["vs_nifty"]["average_gap_points"]},
                   "byMonth": body["by_month"], "lines": body["lines"]}}


def sale_lot(db, symbol, buy_on, buy_qty, buy_price, sell_on, sell_qty, sell_price, placed_by=None, expenses=0.0):
    isin = f"INE{abs(hash(symbol)) % 1000:03d}X01011" if False else f"INE{symbol[:3]:>3}00000"[:12]
    key = f"{symbol}{buy_on}buy"
    db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, currency, closed_quantity, source, "
               "source_ref) values ('stock', ?, ?, ?, ?, ?, 'INR', ?, 'trades:test', ?)",
               [symbol, isin, buy_on, buy_qty, buy_price, min(buy_qty, sell_qty), key])
    db.execute("insert into sales (kind, symbol, isin, sold_on, quantity, price_per_unit, currency, expenses, source, source_ref) "
               "values ('stock', ?, ?, ?, ?, ?, 'INR', ?, 'trades:test', ?)", [symbol, isin, sell_on, sell_qty, sell_price, expenses,
                                                                              f"{symbol}{sell_on}sell"])
    if placed_by:
        db.execute("insert into trade_tags values (?, ?, ?, 'test')", [key, placed_by, "Value" if placed_by == "smallcase" else None])


def record_cases():
    out = []
    AS_OF = date(2025, 12, 31)

    def close(symbol, day, value):
        return (day, symbol, "NSE", "EQ", value, value, value, value, value, 1000, 1e6, 10)

    def hand(db):
        buy = date(2025, 1, 10)
        sale_lot(db, "XXX", buy, 10, 100, date(2025, 3, 10), 10, 130)
        sale_lot(db, "YYY", buy, 10, 100, date(2025, 2, 10), 10, 120)
        sale_lot(db, "ZZZ", buy, 10, 100, date(2025, 7, 10), 10, 80)
        sale_lot(db, "SSS", buy, 5, 50, date(2025, 4, 10), 5, 70, placed_by="smallcase")
        insert_prices(db, [close("XXX", date(2025, 6, 9), 150), close("YYY", date(2025, 5, 12), 110)])
        for day, level in [(buy, 20000), (date(2025, 2, 10), 20400), (date(2025, 3, 10), 21000), (date(2025, 7, 10), 19000)]:
            db.execute("insert into index_levels values (?, 'Nifty 50', ?, 20, 3, 1)", [day, level])
    out.append(record_case("hand example: three closed trades, the smallcase one is not his", hand, AS_OF))
    out.append(record_case("nothing closed yet", lambda db: None, AS_OF))

    def winners_only(db):
        sale_lot(db, "AAA", date(2025, 1, 10), 10, 100, date(2025, 2, 10), 10, 130)
        sale_lot(db, "BBB", date(2025, 1, 10), 10, 100, date(2025, 3, 10), 10, 120)
        sale_lot(db, "CCC", date(2025, 1, 10), 10, 100, date(2025, 3, 11), 10, 111)
        db.execute("insert into index_levels values ('2025-01-10', 'Nifty 50', 20000, 20, 3, 1)")
    out.append(record_case("winners only: no loser line", winners_only, AS_OF))
    rng = random.Random(31)
    for c in range(70):
        def build(db, rng=rng):
            index_day = date(2024, 12, 1)
            levels = []
            level = 20000.0
            for k in range(0, 520, rng.choice([1, 3, 7])):
                level *= 1 + rng.uniform(-0.01, 0.012)
                levels.append((index_day + timedelta(days=k), round(level, 2)))
            for d, v in levels:
                db.execute("insert into index_levels values (?, 'Nifty 50', ?, 20, 3, 1)", [d, v])
            price_rows = []
            for i in range(rng.randint(2, 9)):
                sym = f"Q{c}{i}"
                buy_on = date(2025, 1, 1) + timedelta(days=rng.randint(0, 150))
                sell_on = buy_on + timedelta(days=rng.randint(1, 260))
                bq = rng.choice([5, 10, 25.5, 100])
                sq = rng.choice([bq, bq, bq / 2])
                bp = round(rng.uniform(20, 900), 2)
                sp = round(bp * rng.uniform(0.6, 1.5), 2)
                sale_lot(db, sym, buy_on, bq, bp, sell_on, sq, sp, placed_by=rng.choice([None, None, "smallcase"]),
                         expenses=rng.choice([0.0, 12.5]))
                if rng.random() < 0.8:
                    price_rows.append(close(sym, sell_on + timedelta(days=rng.randint(85, 100)), round(sp * rng.uniform(0.7, 1.4), 2)))
            if price_rows:
                insert_prices(db, price_rows)
        out.append(record_case(f"random {c}", build, rng.choice([date(2025, 12, 31), date(2025, 9, 30), date(2026, 6, 30)])))
    return out


def acted_cases(seed=11):
    from stockpilot.book import acted
    out = []
    rng = random.Random(seed)
    for c in range(60):
        db = new_db()
        holidays = sorted({date(2026, 1, 1) + timedelta(days=rng.randint(0, 120)) for _ in range(rng.randint(0, 8))})
        for h in holidays:
            db.execute("insert into holidays values (?, 'h')", [h])
        symbols = ["AAA", "BBB", "CCC"]
        calls = []
        for i in range(rng.randint(1, 8)):
            made = date(2026, 1, 5) + timedelta(days=rng.randint(0, 100))
            kind = rng.choice(["buy", "add", "sell", "trim", "hold", "watch", None])
            sym = rng.choice(symbols)
            if rng.random() < 0.7:
                db.execute("insert into calls (made_on, symbol, kind, action, section) values (?, ?, ?, ?, ?)", [made, sym, "x", kind, None])
            else:
                db.execute("insert into calls (made_on, symbol, kind, action, section) values (?, ?, ?, ?, ?)", [made, sym, "x", "buy", kind])
            if rng.random() < 0.1:
                db.execute("update calls set acted_on = ? where id = (select max(id) from calls)", [made + timedelta(days=1)])
        confirmed = []
        for i in range(rng.randint(0, 10)):
            day = date(2026, 1, 5) + timedelta(days=rng.randint(0, 130))
            side = rng.choice(["buy", "BUY", "sell", "Sell", "credit"])
            sym = rng.choice(symbols)
            db.execute("insert into trades (trade_key, source, source_ref, kind, symbol, isin, side, trade_date, quantity, price, status) "
                       "values (?, 's', 'r', 'stock', ?, 'I', ?, ?, 1, 1, ?)", [f"k{i}", sym, side, day, rng.choice(["confirmed", "confirmed", "expected"])])
        syncs = []
        for i in range(rng.randint(0, 3)):
            rows = []
            for _ in range(rng.randint(0, 5)):
                day = date(2026, 1, 5) + timedelta(days=rng.randint(0, 130))
                stamp = rng.choice([f"{day} 10:15:00", f"{day}T10:15:00", f"{day}", None, "garbage"])
                rows.append({"tradingsymbol": rng.choice(["aaa", "BBB", "ccc", None]), "transaction_type": rng.choice(["BUY", "SELL", "buy", "x"]),
                             rng.choice(["fill_timestamp", "order_timestamp", "exchange_timestamp"]): stamp})
            syncs.append(rows)
            db.execute("insert into kite_syncs (fetched_at, trades) values (?, ?)", [datetime(2026, 5, 1, i), json.dumps(rows)])
        open_calls = [{"id": i, "symbol": s, "madeOn": str(m), "kind": k} for i, s, m, k in db.execute(
            "select id, symbol, made_on, coalesce(section, action) from calls where acted_on is null and made_on is not null order by id").fetchall()]
        conf = [{"symbol": s, "side": side, "tradeDate": str(d)} for s, side, d in db.execute(
            "select symbol, lower(side), trade_date from trades where status = 'confirmed' and lower(side) in ('buy', 'sell')").fetchall()]
        n = acted.mark(db)
        after = db.execute("select id, acted_on from calls where acted_on is not null order by id").fetchall()
        out.append({"input": {"openCalls": open_calls, "confirmedTrades": conf, "kiteSyncs": syncs,
                              "holidays": [str(h) for h in holidays]},
                    "output": {"marked": n, "actedOn": [[i, str(d)] for i, d in after
                                                         if i in {c["id"] for c in open_calls}]}})
    return out


def main():
    check = "--check" in sys.argv
    files = {"lots.json": lots_cases(), "positions.json": positions_cases(), "dust.json": dust_cases(),
             "record.json": record_cases(), "acted.json": acted_cases(), "rounding.json": [rounding_cases()]}
    OUT.mkdir(parents=True, exist_ok=True)
    bad = []
    for name, body in files.items():
        text = "[\n" + ",\n".join(json.dumps(c, sort_keys=True, separators=(",", ":")) for c in body) + "\n]\n"
        path = OUT / name
        if check:
            if not path.exists() or path.read_text() != text:
                bad.append(name)
        else:
            path.write_text(text)
            print(f"wrote {path.relative_to(ROOT)} ({len(body)} cases)")
    if bad:
        print("captured files out of date:", ", ".join(bad))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
