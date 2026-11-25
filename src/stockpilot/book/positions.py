"""What the account holds today. Quantity and cost come from the lots (built from the owners' documents); Kite and
the CDSL statement are the check, and fill a holding the lots do not have yet (an IPO allotment, a demerger).
Every reader of holdings (calls, Portfolio tab, allocation) reads them here."""
from dataclasses import dataclass, field
from datetime import date

from stockpilot import valuation

from stockpilot.sources import fx

from stockpilot.analysis import tax
from stockpilot.book import kinds


@dataclass
class Lot:
    acquired_on: date
    quantity: float               # still open
    cost: float                   # rupees per unit (a US lot: dollars times the rate of its vest day)
    turns_long_term_on: date | None

    def long_term(self, on: date) -> bool:
        return bool(self.turns_long_term_on and on >= self.turns_long_term_on)


@dataclass
class Position:
    kind: str                     # equity | mf | foreign
    symbol: str
    isin: str | None
    name: str
    quantity: float
    avg_cost: float | None        # rupees per unit; None when no document gives a cost
    price: float | None           # rupees per unit on the day; None when no price is stored
    source: str                   # lots | kite | statement
    lots: list[Lot] = field(default_factory=list)
    check: str | None = None      # what Kite or the statement says when it differs from the lots

    @property
    def value(self) -> float:
        return self.quantity * (self.price or self.avg_cost or 0)


def last_kite_sync(db):
    return db.execute("select max(snapshot_at) from holdings").fetchone()[0]


def _funds_by_isin(db) -> dict:
    """ISIN (growth or reinvest) -> (scheme code, name, plan, option, category): what `valuation.fund_for` gives, in one query."""
    out = {}
    for row in db.execute("select scheme_code, name, plan, option, category, isin_growth, isin_reinvest from funds").fetchall():
        for isin in row[5:]:
            if isin:
                out.setdefault(isin, row[:5])
    return out


def _bucket(funds, kind, isin, currency, acquired_on) -> str:
    if kinds.canon(kind) == "mf":
        fund = funds.get(isin)
        return tax.mf_bucket(fund[4] if fund else None, acquired_on, fund[1] if fund else "")
    return tax.bucket_of({"kind": kind, "currency": currency})


DUST_INR = 1000.0     # a holding worth less than this is a leftover (0.195 units of a liquid fund), not shown
FOREIGN_NAMES = {"US81762P1021": "ServiceNow"}     # the owner's employer: the only foreign share held


def _identity(db):
    """(kind, isin, fallback symbol) -> (symbol, name). Exchange-traded holdings (ETFs too) keep their NSE symbol;
    a fund's symbol is its ISIN, as Kite reports it."""
    stocks = {i: (s, n) for s, n, i in db.execute("select symbol, name, isin from stocks where isin is not null").fetchall()}
    funds = dict(db.execute("select isin_growth, name from funds where isin_growth is not null").fetchall())

    def ident(kind, isin, fallback):
        if isin in FOREIGN_NAMES:
            return fallback, FOREIGN_NAMES[isin]
        if kind == "mf":
            return (isin or fallback), funds.get(isin, fallback)
        symbol, name = stocks.get(isin, (fallback, None))
        return symbol, name or funds.get(isin) or symbol
    return ident


def _kite(db) -> dict:
    snap = last_kite_sync(db)
    rows = db.execute("select kind, symbol, isin, sum(quantity), sum(quantity * avg_price) / sum(quantity) from holdings "
                      "where snapshot_at = ? and quantity > 0 group by all", [snap]).fetchall() if snap else []
    return {(kinds.canon(k), i or s): (s, q, a) for k, s, i, q, a in rows}


def _statement(db) -> dict:
    as_of = db.execute("select max(as_of) from holding_statements").fetchone()[0]
    return dict(db.execute("select isin, quantity from holding_statements where as_of = ? and quantity > 0",
                           [as_of]).fetchall()) if as_of else {}


def _u(n: float) -> str:
    return f"{n:.2f}".rstrip("0").rstrip(".")


def _by_kite(kite_qty: float, kite_avg: float, lot_qty: float, lots: list[Lot], lot_cost: float | None):
    """(units, rupee cost per unit, lots, source, check) of a holding both Kite and the documents know. Kite's units win.
    Units the documents do not explain are costed so the total matches Kite's average; units the documents show beyond
    Kite's were sold without a document, and the oldest lots go first (FIFO)."""
    if abs(kite_qty - lot_qty) < 1e-6:
        return kite_qty, lot_cost, lots, "lots", None
    if lot_qty < kite_qty:
        gap, cost = kite_qty - lot_qty, kite_avg
        if lot_cost is not None and kite_avg:
            rest = (kite_avg * kite_qty - lot_cost * lot_qty) / gap
            cost = (lot_cost * lot_qty + (rest if rest > 0 else kite_avg) * gap) / kite_qty
        return kite_qty, cost if cost is not None else lot_cost, lots, "kite", f"Documents explain {_u(lot_qty)} of {_u(kite_qty)} units."
    left, kept = lot_qty - kite_qty, []
    for l in lots:                          # oldest first
        cut = min(l.quantity, left)
        left -= cut
        if l.quantity - cut > 1e-9:
            kept.append(Lot(l.acquired_on, l.quantity - cut, l.cost, l.turns_long_term_on))
    cost = sum(l.quantity * l.cost for l in kept) / kite_qty if kept and all(l.cost is not None for l in kept) else kite_avg
    return kite_qty, cost, kept, "lots", f"Documents show {_u(lot_qty)} units; Kite shows {_u(kite_qty)}."


def without_dust(positions: list[Position]) -> list[Position]:
    """Drops a leftover worth under DUST_INR that only a depository statement knows (0.195 units of a liquid fund). A holding
    Kite or a document shows stays whatever its size, and one with no price is kept: a gap must never hide a holding."""
    return [p for p in positions if p.source != "statement" or p.price is None or p.value >= DUST_INR]


def held(db, as_of: date) -> list[Position]:
    ident, rate, funds = _identity(db), fx.usdinr_on(db, as_of), _funds_by_isin(db)
    rate_on = fx.rate_on(db)
    grouped: dict[tuple, dict] = {}
    for kind, symbol, isin, acquired_on, qty, cost, currency, estimated in db.execute(
            "select kind, symbol, isin, acquired_on, quantity - closed_quantity, cost_per_unit, coalesce(currency, 'INR'), "
            "coalesce(estimated, false) "
            "from lots where quantity - closed_quantity > 1e-9 order by acquired_on, id").fetchall():
        k = kinds.canon(kind)
        g = grouped.setdefault((k, isin or symbol), {"kind": k, "symbol": symbol, "isin": isin, "lots": [],
                                                     "foreign": False, "estimated": 0.0})
        g["estimated"] += qty if estimated else 0.0
        foreign = kinds.is_foreign({"kind": kind, "currency": currency})
        g["foreign"] |= foreign
        if foreign:   # each lot at the rate of its own day; the nearest earlier rate, else today's, else no cost at all
            day_rate = rate_on(acquired_on) or rate
            cost = cost * day_rate if day_rate else None
        g["lots"].append(Lot(acquired_on, qty, cost, tax.turns_long_term_on(_bucket(funds, kind, isin, currency, acquired_on),
                                                                             acquired_on)))
    kite, statement = _kite(db), _statement(db)
    out, items = [], []
    for key, g in grouped.items():
        lots = g["lots"]
        qty = sum(l.quantity for l in lots)
        cost = (sum(l.quantity * l.cost for l in lots) / qty) if all(l.cost is not None for l in lots) else None
        symbol, name = ident(g["kind"], g["isin"], kite.get(key, (g["symbol"],))[0])   # the NSE list first
        source, check = "lots", None
        if kite and not g["foreign"]:        # Kite decides what is owned and how many units; the lots add cost, dates, tax
            if key not in kite:
                continue                     # Kite has no such holding: the nightly unit check names the gap
            qty, cost, lots, source, check = _by_kite(kite[key][1], kite[key][2], qty, lots, cost)
        elif not kite and statement and g["isin"] in statement and abs(statement[g["isin"]] - qty) > 1e-6:
            check = f"The depository statement shows {statement[g['isin']]:g}."
        if g["estimated"] > 1e-9:    # units Kite shows that no document explains yet: the lots carry an estimated one
            check = (check + " " if check else "") + (f"Estimated: {_u(g['estimated'])} units are not in a document yet; "
                                                       "their cost is Kite's average price.")
        out.append(Position(g["kind"], symbol, g["isin"], name, qty, cost, None, source, lots, check))
        items.append({"kind": g["kind"], "symbol": g["symbol"], "isin": g["isin"]})
    for (k, kid), (symbol, qty, avg) in kite.items():
        if (k, kid) not in grouped:
            isin = kid if kid != symbol or k == "mf" else None
            symbol, name = ident(k, isin, symbol)
            out.append(Position(k, symbol, isin, name, qty, avg, None, "kite"))
            items.append({"kind": k, "symbol": symbol, "isin": isin})
    have = {p.isin for p in out}
    shares = {i for (i,) in db.execute("select isin from stocks where isin is not null").fetchall()}
    for isin, qty in statement.items():
        # With no Kite snapshot the depository statement fills any gap. With one, only a fund Kite cannot see (held at
        # the depository, not in Coin) is added: a share or ETF Kite lacks was sold since the statement.
        if isin not in have and (not kite or (isin.startswith("INF") and isin in funds and isin not in shares)):
            kind = "mf" if isin.startswith("INF") else "equity"
            symbol, name = ident(kind, isin, isin)
            out.append(Position(kind, symbol, isin, name, qty, None, None, "statement"))
            items.append({"kind": kind, "symbol": symbol, "isin": isin})
    for p, price in zip(out, valuation.unit_prices_inr(db, items, as_of, {i: f[0] for i, f in funds.items()}, rate)):
        p.price = price
    return sorted(without_dust(out), key=lambda p: -p.value)
