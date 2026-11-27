"""Zerodha Console tradebook CSV (the baseline). Columns: symbol, isin, trade_date, exchange, segment,
series, trade_type, auction, quantity, price, trade_id, order_id, order_execution_time. Equity and mutual fund (MF) rows only."""
import csv
import io
from datetime import date

from stockpilot.trades.lots import Trade


def parse(text: str) -> list[Trade]:
    out = []
    for row in csv.DictReader(io.StringIO(text.lstrip("﻿"))):
        segment = (row.get("segment") or "").strip().upper()
        side = row["trade_type"].strip().lower()
        if segment not in ("EQ", "MF") or side not in ("buy", "sell"):
            continue
        if segment == "MF":   # keyed like the Coin allotment mail, so one purchase counts once
            day, qty = date.fromisoformat(row["trade_date"].strip()[:10]), float(row["quantity"])
            out.append(Trade("tradebook", row["trade_id"].strip(), "mf", row["symbol"].strip(), row["isin"].strip(),
                             side, day, qty, float(row["price"]), trade_key=f"mf:{day}:{row['isin'].strip()}:{side}:{qty:g}"))
            continue
        out.append(Trade("tradebook", row["trade_id"].strip(), "stock", row["symbol"].strip(),
                         row["isin"].strip() or None, side, date.fromisoformat(row["trade_date"].strip()[:10]),
                         float(row["quantity"]), float(row["price"]), trade_key=row["trade_id"].strip()))
    return out
