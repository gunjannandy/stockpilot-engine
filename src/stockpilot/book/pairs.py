"""The father's trades and smallcase's, matched buy to sell. Shared by the smallcase comparison and his own record.

Each row pairs a lot with a sale (first in, first out, as tax.py does) and carries the route that bought the lot:
`kite` (Dad placed it) or `smallcase`. Lots are in today's share units, so prices from `analytics` line up with
them. Stocks only: funds and RSUs are a different question."""
from bisect import bisect_right
from datetime import date

from stockpilot.analysis import analytics, tax
from stockpilot.book import kinds


def load(db):
    """(lots, sales, pairs): `pairs` are tax.realise rows plus "route" and "basket"; lots carry "route" too."""
    lots = []
    for (lid, kind, symbol, isin, on, qty, cost, cur, ref, placed_by, basket) in db.execute(
            "select l.id, l.kind, l.symbol, l.isin, l.acquired_on, l.quantity, l.cost_per_unit, "
            "coalesce(l.currency, 'INR'), l.source_ref, t.placed_by, t.basket from lots l "
            "left join trade_tags t on t.trade_key = l.source_ref order by l.acquired_on, l.id").fetchall():
        if kinds.canon(kind) == "equity" and cur == "INR":
            lots.append({"id": lid, "kind": kind, "symbol": symbol, "isin": isin, "acquired_on": on, "quantity": qty,
                         "cost_per_unit": cost, "currency": cur, "route": placed_by, "basket": basket})
    first = {}
    for lot in lots:   # free shares (a bonus) take the route of the first lot of that stock
        if lot["route"]:
            first.setdefault(lot["isin"] or lot["symbol"], (lot["route"], lot["basket"]))
    for lot in lots:
        if not lot["route"]:
            lot["route"], lot["basket"] = first.get(lot["isin"] or lot["symbol"], ("kite", None))
    sales = [{"id": sid, "kind": kind, "symbol": symbol, "isin": isin, "sold_on": on, "quantity": qty,
              "price_per_unit": price, "currency": cur, "expenses": exp or 0}
             for sid, kind, symbol, isin, on, qty, price, cur, exp in db.execute(
                 "select id, kind, symbol, isin, sold_on, quantity, price_per_unit, coalesce(currency, 'INR'), expenses "
                 "from sales order by sold_on, id").fetchall()
             if kinds.canon(kind) == "equity" and (cur or "INR") == "INR"]
    by_id = {l["id"]: l for l in lots}
    pairs = []
    for row in tax.realise(lots, sales):
        lot = by_id[row["lot_id"]]
        pairs.append({**row, "route": lot["route"], "basket": lot["basket"]})
    return lots, sales, pairs


class Series:
    """A sorted (date, value) list that answers "the last value on or before a day"."""

    def __init__(self, rows):
        self.days = [d for d, _ in rows]
        self.values = [v for _, v in rows]

    def on(self, day: date):
        i = bisect_right(self.days, day)
        return self.values[i - 1] if i else None

    def near(self, day: date, within: int = 7):
        """The value on `day`, or on a day up to `within` days earlier; None when the series has nothing that close."""
        i = bisect_right(self.days, day)
        return self.values[i - 1] if i and (day - self.days[i - 1]).days <= within else None


def prices_for(db, symbols, since: date) -> dict:
    return {s: Series(analytics.adjusted_closes(db, s, since)) for s in symbols}


def nifty(db) -> Series:
    return Series(db.execute("select date, close from index_levels where name = 'Nifty 50' order by date").fetchall())
