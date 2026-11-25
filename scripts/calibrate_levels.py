"""Rebuild config/levels_calibration.json from the price history. Read-only on the database; one chunk of stocks at a time.
Run: uv run python scripts/calibrate_levels.py [--db data/stockpilot.duckdb] [--out config/levels_calibration.json]"""
import argparse
import json
import sys
from collections import defaultdict
from datetime import date, timedelta

import duckdb

from stockpilot import levels_calibration as cal
from stockpilot.analysis import analytics

CHUNK = 60


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default="data/stockpilot.duckdb")
    ap.add_argument("--out", default=str(cal.PATH))
    ap.add_argument("--step", type=int, default=5)
    a = ap.parse_args()
    db = duckdb.connect(a.db, read_only=True, config={"memory_limit": "400MB", "threads": 1})
    since = date.today() - timedelta(days=365 * 6)
    symbols = [r[0] for r in db.execute("select symbol from prices where exchange='NSE' and date >= ? group by symbol having count(*) > 400 order by symbol", [since]).fetchall()]
    per_bucket, n_stocks = defaultdict(list), 0
    for k in range(0, len(symbols), CHUNK):
        part = symbols[k:k + CHUNK]
        sql = analytics.ADJUSTED_SQL.format(symbol_filter="and exchange = 'NSE' and symbol in (select unnest($symbols))")
        rows = db.execute(f"""select p.symbol, p.high * a.adj_close / p.close, p.low * a.adj_close / p.close, a.adj_close, p.value
            from ({sql}) a join prices p on p.symbol = a.symbol and p.exchange = a.exchange and p.date = a.date
            where p.close > 0 and p.high > 0 and p.low > 0 order by p.symbol, p.date""", {"since": since, "symbols": part}).fetchall()
        by = defaultdict(list)
        for r in rows:
            by[r[0]].append(r[1:])
        for sym, rs in by.items():
            h, l, c, v = ([r[i] for r in rs] for i in range(4))
            outs = cal.measure_series(h, l, c, step=a.step)
            if not outs:
                continue
            n_stocks += 1
            for o in outs:
                i = o["i"]
                atr = cal._atr(h, l, c, i)
                vals = [x or 0 for x in v[i - 62:i + 1]]
                per_bucket[cal.bucket(atr / c[i], sum(vals) / len(vals) / 1e7)].append(o)
        print(f"{min(k + CHUNK, len(symbols))}/{len(symbols)}", file=sys.stderr, flush=True)
    out = cal.build(per_bucket)
    out["measured_on"], out["stocks"] = str(date.today()), n_stocks
    json.dump(out, open(a.out, "w"), indent=1)
    print(json.dumps({b: {k: v for k, v in e.items() if k != "curve"} for b, e in out["buckets"].items()}, indent=1))


if __name__ == "__main__":
    main()
