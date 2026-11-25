"""Helpers for the verify tests (a module of its own: two files named conftest cannot be imported by name side by side)."""
import json
from datetime import date, timedelta

DAY = date(2026, 11, 20)


def bdays(end, n):
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return out[::-1]


def price_rows(symbol, closes, end=DAY, exchange="NSE", value=5e8):
    days = bdays(end, len(closes))
    rows, prev = [], closes[0]
    for d, c in zip(days, closes):
        rows.append((d, symbol, exchange, "EQ", prev, c, c, c, prev, 1_000_000, value, 5000))
        prev = c
    return rows


def read(site, name):
    return json.loads((site / "data" / f"{name}.json").read_text())


def write(site, name, body):
    (site / "data" / f"{name}.json").write_text(json.dumps(body, default=str, separators=(",", ":")))
