"""Allocation against the target the owners approved, by asset class, in rupees."""
from datetime import date

import duckdb

from stockpilot import valuation
from stockpilot.book import positions

LABELS = {"stocks": "Indian stocks", "equity_funds": "Equity funds", "debt_funds": "Debt funds",
          "gold": "Gold", "foreign": "US shares (RSUs)", "other_funds": "Other funds"}
CLOSE_ENOUGH = 0.02    # within 2% of the total is "on target"


def asset_class(db, h: dict) -> str:
    if h["kind"] == "equity":
        return "stocks"
    if h["kind"] == "foreign":
        return "foreign"
    fund = valuation.fund_for(db, h["isin"])
    category = ((fund and fund[4]) or "").lower()
    if category.startswith("equity scheme") or "arbitrage" in category or "aggressive" in category:
        return "equity_funds"
    if category.startswith("debt scheme"):
        return "debt_funds"
    if "gold" in category:
        return "gold"
    return "other_funds"


def compare(db: duckdb.DuckDBPyConnection, as_of: date, target: dict | None) -> dict:
    values: dict[str, float] = {}
    unpriced = []
    for p in positions.held(db, as_of):
        if p.price is None:
            unpriced.append(p.symbol)
            continue
        cls = asset_class(db, {"kind": p.kind, "isin": p.isin})
        values[cls] = values.get(cls, 0) + p.quantity * p.price
    total = sum(values.values())
    rows = []
    for cls in sorted(set(values) | set(target or {}), key=lambda c: -values.get(c, 0)):
        value, share = values.get(cls, 0.0), (values.get(cls, 0.0) / total if total else 0.0)
        row = {"class": cls, "label": LABELS.get(cls, cls), "value": value, "share": share,
               "target": None, "gap_inr": None, "action": ""}
        if target:
            row["target"] = target.get(cls, 0.0)
            row["gap_inr"] = row["target"] * total - value
            gap = row["gap_inr"]
            row["action"] = ("On target" if abs(gap) <= CLOSE_ENOUGH * total
                             else f"{'Add' if gap > 0 else 'Trim'} ₹{abs(gap):,.0f}")
        rows.append(row)
    return {"as_of": as_of, "total": total, "target_set": bool(target), "rows": rows, "unpriced": unpriced}
