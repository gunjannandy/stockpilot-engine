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


def main():
    check = "--check" in sys.argv
    files = {"lots.json": lots_cases()}
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
