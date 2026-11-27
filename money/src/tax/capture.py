"""Capture today's Python tax outputs as fixtures for the TypeScript port (MONEYTAX).

    cd py && uv run --frozen python ../money/src/tax/capture.py

Every row is made up; nothing reads the vault. Writes money/captured/tax.json and itr.json.
Shapes stay snake_case, as in the Python. `--check` fails when a saved file would change."""
import json
import math
import random
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "py"))

from stockpilot.analysis import tax  # noqa: E402

OUT = ROOT / "money" / "captured"


def j(v):
    if isinstance(v, date):
        return str(v)
    if isinstance(v, float) and math.isinf(v):
        return "inf"
    if isinstance(v, dict):
        return {k: j(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [j(x) for x in v]
    if hasattr(v, "__dataclass_fields__"):
        return j(v.__dict__)
    return v


def d(s):
    return date.fromisoformat(s) if isinstance(s, str) else s


def lot_in(l):
    return {**l, "acquired_on": d(l["acquired_on"])}


def sale_in(s):
    return {**s, "sold_on": d(s["sold_on"])}


def table_rate(table):
    def rate_on(day):
        ks = [k for k in table if d(k) <= day]
        return table[max(ks)] if ks else None
    return rate_on


def run(fn):
    try:
        return {"ok": j(fn())}
    except (tax.OversoldError, tax.MissingRate, ValueError) as e:
        return {"error": type(e).__name__}


ISINS = ["INE001A01036", "INE002A01018", "INE003A01024", "INE004A01022", "US0378331005"]
FX = {"2016-01-01": 66.0, "2023-01-01": 82.5, "2024-01-01": 83.1, "2024-12-31": 85.6, "2025-06-30": 85.7, "2026-01-31": 90.2}


def rand_world(rng):
    lots, sales = [], []
    n = rng.randint(1, 6)
    for i in range(n):
        isin = rng.choice(ISINS)
        foreign = isin.startswith("US")
        kind = "rsu" if foreign else rng.choice(["stock", "stock", "mf"])
        acquired = date(2016, 1, 1) + timedelta(days=rng.randint(0, 3600))
        lot = {"id": i + 1, "symbol": "S" + isin[3:6], "isin": isin, "kind": kind, "acquired_on": str(acquired),
               "quantity": float(rng.randint(1, 200)), "cost_per_unit": round(rng.uniform(20, 900), 2),
               "currency": "USD" if foreign else "INR"}
        if kind == "mf" and rng.random() < 0.6:
            lot["bucket"] = rng.choice(["equity", "other", "specified_mf", "gold_etf"])
        lots.append(lot)
    for lot in list(lots):
        if rng.random() < 0.8:
            sold = d(lot["acquired_on"]) + timedelta(days=rng.randint(10, 2600))
            if sold > date(2026, 11, 1):
                continue
            qty = float(max(1, int(lot["quantity"] * rng.uniform(0.2, 1.0))))
            if rng.random() < 0.05:
                qty += 500
            sales.append({"symbol": lot["symbol"], "isin": lot["isin"], "sold_on": str(sold), "quantity": qty,
                          "price_per_unit": round(lot["cost_per_unit"] * rng.uniform(0.5, 2.2), 2),
                          "currency": lot["currency"], "expenses": round(rng.uniform(0, 80), 2) if rng.random() < .5 else 0})
    fmv = {l["isin"]: round(l["cost_per_unit"] * rng.uniform(0.7, 1.6), 2) for l in lots if rng.random() < 0.6}
    return lots, sales, fmv


def cases():
    rng = random.Random(20261127)
    out = {"rules_for": [], "classify": [], "income_tax": [], "slab_tax": [], "realise": [], "net_gains": [],
           "harvest": [], "schedule_fa": [], "fy": []}
    for fy in (2023, 2024, 2025, 2026, 2027, 2030):
        out["rules_for"].append({"fy": fy, "output": run(lambda: tax.rules_for(fy))})
    for dd in ("2025-03-31", "2025-04-01", "2025-12-31", "2026-01-01", "2024-02-29"):
        out["fy"].append({"day": dd, "fy": tax.fy_of(d(dd)), "label": tax.fy_label(tax.fy_of(d(dd)))})
    for bucket in ("equity", "gold_etf", "other", "foreign", "specified_mf"):
        for _ in range(12):
            a = date(2018, 1, 1) + timedelta(days=rng.randint(0, 3000))
            s = a + timedelta(days=rng.choice([0, 364, 365, 366, 729, 730, 731, rng.randint(0, 1200)]))
            out["classify"].append({"bucket": bucket, "acquired_on": str(a), "sold_on": str(s),
                                    "term": tax.term(bucket, a, s), "long_on": j(tax.turns_long_term_on(bucket, a))})
    for _ in range(12):
        out["classify"].append({"grand": [100.0, 150.0, 120.0], "out": tax.grandfathered_cost(100.0, 150.0, 120.0)})
    for cat, name in [("Equity Scheme - Large Cap", ""), ("Hybrid Scheme - Arbitrage", ""), ("Hybrid Scheme - Balanced", ""),
                      ("Debt Scheme - Gilt", ""), ("Other Scheme - Index Funds", "Nifty 50 Index"), (None, "Gold ETF"),
                      ("Other Scheme - FoF Overseas", "x"), (None, "")]:
        for dd in ("2022-01-01", "2024-01-01"):
            out["classify"].append({"mf": [cat, dd, name], "out": tax.mf_bucket(cat, d(dd), name)})
    rules = tax.rules_for(2026)
    for inc in [0, 399999, 400000, 1_000_000, 1_200_000, 1_200_001, 1_270_000, 2_500_000, 6_000_000, 30_000_000]:
        out["slab_tax"].append({"income": inc, "tax": tax.slab_tax(inc, rules)})
    pts = [0, 500_000, 1_200_000, 1_250_000, 4_900_000, 5_000_001, 5_100_000, 10_000_001, 10_300_000, 20_000_001, 21_000_000, 80_000_000]
    for _ in range(80):
        args = {"slab_income": rng.choice(pts) if rng.random() < .8 else 0, "stcg_equity": rng.choice([0, 0, 50_000, 900_000, 6_000_000]),
                "ltcg_equity": rng.choice([0, 100_000, 125_000, 700_000, 9_000_000]),
                "ltcg_other": rng.choice([0, 0, 40_000, 3_000_000]), "dividend": rng.choice([0, 0, 30_000, 4_000_000])}
        out["income_tax"].append({"args": args, "output": j(tax.income_tax(rules=rules, **args))})
    for _ in range(70):
        lots, sales, fmv = rand_world(rng)
        L, S = [lot_in(l) for l in lots], [sale_in(s) for s in sales]
        rate = table_rate(FX)
        rule = rng.choice(["prior_month_end", "same_day"])
        out["realise"].append({"lots": lots, "sales": sales, "fmv_2018": fmv, "fx": FX, "fx_rule": rule,
                               "output": run(lambda: tax.realise(L, S, fmv, rate, rule)),
                               "open": run(lambda: tax.open_lots(L, S))})
        got = run(lambda: tax.realise(L, S, fmv, rate, rule))
        if "ok" in got:
            rows = tax.realise(L, S, fmv, rate, rule)
            carried = rng.choice([None, [{"year": 2020, "stcl": 30000.0, "ltcl": 10000.0}, {"year": 2023, "stcl": 0.0, "ltcl": 60000.0}]])
            for fy in (2025, 2026):
                r = tax.rules_for(fy)
                net = tax.net_gains(rows, r, fy, carried)
                out["net_gains"].append({"rows": j(rows), "fy": fy, "carried": carried, "output": j(net),
                                         "inputs": j(tax.inputs(net, 250_000)),
                                         "tax": j(tax.income_tax(**tax.inputs(net, 250_000), rules=r))})
        open_ = [l for l in L]
        prices = {l["symbol"]: round(l["cost_per_unit"] * rng.uniform(0.6, 2.5), 2) for l in lots if rng.random() < .8}
        as_of = d("2026-11-27")
        realised = rng.choice([0, 40_000.0, 200_000.0])
        out["harvest"].append({"lots": lots, "prices": prices, "as_of": str(as_of), "realised": realised,
                               "output": j(tax.harvest(open_, prices, as_of, rules, realised))})
        closes = {}
        for l in lots:
            if rng.random() < .7:
                closes[l["symbol"]] = {str(date(2025, 1, 1) + timedelta(days=k)): round(rng.uniform(100, 300), 2) for k in (3, 100, 200, 360)}
        for cy in (2024, 2025):
            out["schedule_fa"].append({"lots": lots, "sales": sales, "cy": cy, "closes": closes, "fx": FX,
                                       "output": run(lambda: tax.schedule_fa(L, S, cy, {s: {d(k): v for k, v in c.items()} for s, c in closes.items()}, table_rate(FX)))})
    return out


def packs():
    rng = random.Random(77)
    res = []
    for _ in range(25):
        lots, sales, fmv = rand_world(rng)
        L, S = [lot_in(l) for l in lots], [sale_in(s) for s in sales]
        closes = {l["symbol"]: {str(date(2025, 1, 1) + timedelta(days=k)): round(rng.uniform(100, 300), 2) for k in (3, 100, 200, 360)}
                  for l in lots if rng.random() < .7}
        fy = rng.choice([2024, 2025, 2026])
        carried = rng.choice([None, [{"year": 2021, "stcl": 20000.0, "ltcl": 5000.0}]])
        slab = rng.choice([0, 900_000])
        tmp = Path(tempfile.mkdtemp())
        try:
            r = tax.build_pack(L, S, fy, tmp, table_rate(FX), {s: {d(k): v for k, v in c.items()} for s, c in closes.items()},
                               fmv, carried, slab, fx_note="test rates")
        except (tax.OversoldError, tax.MissingRate, ValueError) as e:
            res.append({"lots": lots, "sales": sales, "fy": fy, "closes": closes, "fmv_2018": fmv, "fx": FX, "carried": carried,
                        "slab_income": slab, "output": {"error": type(e).__name__}})
            continue
        files = {n: (tmp / n).read_text() for n in ("gains_detail.csv", "schedule_112a.csv", "schedule_fa.csv", "summary.json", "README.txt")}
        res.append({"lots": lots, "sales": sales, "fy": fy, "closes": closes, "fmv_2018": fmv, "fx": FX, "carried": carried,
                    "slab_income": slab, "output": {"files": files, "itr_form": r["itr_form"]}})
    return res


def main():
    check = "--check" in sys.argv
    body = {"tax.json": [cases()], "itr.json": packs()}
    bad = []
    for name, cs in body.items():
        text = "[\n" + ",\n".join(json.dumps(c, sort_keys=True, separators=(",", ":")) for c in cs) + "\n]\n"
        p = OUT / name
        if check:
            if not p.exists() or p.read_text() != text:
                bad.append(name)
        else:
            p.write_text(text)
            print("wrote", p.relative_to(ROOT), len(cs))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
