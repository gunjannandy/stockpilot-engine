"""Trades in, lots out. Lots are derived: rebuild() replays every confirmed trade and corporate action
in date order (FIFO per ISIN, per tax-rules.md) and rewrites the lots and sales it owns, so it is idempotent and a
late-arriving document or corporate action simply fixes history on the next rebuild.

One story for tax and holdings: `lots.quantity` is the amount bought (in today's share units), `closed_quantity`
is the part sold, and what is held is the difference. Every matched sell is also written to `sales` in the same
units, so tax.py can re-match from scratch and arrive at the same open lots."""
import math
import re
from dataclasses import dataclass
from datetime import date

OWNED = "trades:%"  # lots.source marker for rows this module wrote


@dataclass(frozen=True)
class Trade:
    source: str          # tradebook | contract_note | coin | cas | fidelity | rsu_inference
    source_ref: str      # the document or exchange trade id
    kind: str            # stock | mf | rsu
    symbol: str
    isin: str | None
    side: str            # buy | sell | vest | credit | debit (credit/debit: CAS movements with no price)
    trade_date: date
    quantity: float
    price: float | None
    currency: str = "INR"
    status: str = "confirmed"   # "expected" vests never become lots
    trade_key: str | None = None

    @property
    def key(self) -> str:
        if self.trade_key:
            return self.trade_key
        return f"{self.isin or self.symbol}|{self.trade_date}|{self.side}|{self.quantity:g}|{self.price}"


@dataclass
class Holding:
    kind: str
    symbol: str
    isin: str | None
    quantity: float
    avg_cost: float
    currency: str


@dataclass
class RebuildResult:
    lots: int = 0
    unmatched_sells: list = None

    def __post_init__(self):
        self.unmatched_sells = self.unmatched_sells or []


def save_trades(db, trades) -> int:
    """Insert trades not seen before (by exchange trade id, else by a content key). Returns rows added."""
    added = 0
    for t in trades:
        if db.execute("select 1 from trades where trade_key = ?", [t.key]).fetchone():
            continue
        db.execute(
            "insert into trades (trade_key, source, source_ref, kind, symbol, isin, side, trade_date, quantity,"
            " price, currency, status) values (?,?,?,?,?,?,?,?,?,?,?,?)",
            [t.key, t.source, t.source_ref, t.kind, t.symbol, t.isin, t.side, t.trade_date, t.quantity,
             t.price, t.currency, t.status])
        added += 1
    return added


def _r(x: float) -> float:
    return round(x, 6)


def rebuild(db) -> RebuildResult:
    rows = db.execute(
        "select source, source_ref, kind, symbol, isin, side, trade_date, quantity, price, currency, trade_key"
        " from trades where status = 'confirmed' and side in ('buy', 'sell', 'vest') and price is not null"
        " order by trade_date, id").fetchall()
    actions = db.execute(
        "select a.symbol, a.isin, a.ex_date, a.kind, a.numerator, a.denominator, t.new_isin, t.new_symbol,"
        " t.cost_fraction, t.price, a.source from corporate_actions a left join action_terms t"
        " on t.symbol = a.symbol and t.ex_date = a.ex_date and t.kind = a.kind order by a.ex_date").fetchall()

    rows = _one_company_one_key(rows, dict(db.execute("select symbol, isin from stocks where isin is not null").fetchall()))
    groups: dict[str, list] = {}
    for r in rows:
        key = r[3] if r[2] == "stock" else (r[4] or r[3])
        groups.setdefault(key, []).append(("trade", r[6], 1 if r[5] == "sell" else 0, r))
    for a in actions:
        key = a[1] if a[1] in groups else _company(a[0])
        if key in groups:  # an action with no trades has nothing to adjust
            groups[key].append(("action", a[2], -1, a))

    # a demerger hands lots to another company: parents are replayed first, children then start from those lots
    children = {a[7] for a in actions if _demerger_ready(a) and _company(a[0]) in groups}
    for child in children:
        groups.setdefault(child, [])
    spawned: dict[str, list] = {}
    order = [k for k in groups if k not in children] + [k for k in groups if k in children]

    result, out, sold = RebuildResult(), [], []
    for key in order:
        events = groups[key]
        splits = [(e[3][2], e[3][4] / e[3][5]) for e in events if e[0] == "action" and e[3][3] == "split"]
        # on one day: corporate action first (trades on the ex-date are at post-action prices), buys, then sells
        events.sort(key=lambda e: (e[1], e[2]))
        open_lots: list[dict] = list(spawned.get(key, []))
        for typ, when, _, row in events:
            if typ == "action":
                _apply_action(open_lots, row, when, spawned)
            elif row[5] == "sell":
                left = _sell(open_lots, row[7])
                if left > 1e-9:
                    result.unmatched_sells.append((row[4] or row[3], when, _r(left)))
                if row[7] - left > 1e-9:  # only the matched part: tax needs a lot behind every sale
                    m = math.prod(r for ex, r in splits if ex > when)   # today's share units, like the lots
                    sold.append((row[2], row[3], row[4], when, (row[7] - left) * m, row[8] / m, row[9], row[0], row[10]))
            else:
                open_lots.append({"kind": row[2], "symbol": row[3], "isin": row[4], "on": when, "qty": row[7],
                                  "cost": row[8], "closed": 0.0, "cur": row[9], "src": row[0], "ref": row[10]})
        out.extend(open_lots)
    out = _statement_lots(db, out)
    out.extend(_estimated_lots(db, out))

    db.execute("delete from lots where source like ?", [OWNED])
    for lot in out:
        db.execute(
            "insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, currency,"
            " closed_quantity, source, source_ref, estimated) values (?,?,?,?,?,?,?,?,?,?,?)",
            [lot["kind"], lot["symbol"], lot["isin"], lot["on"], _r(lot["qty"]), _r(lot["cost"]), lot["cur"],
             _r(lot["closed"]), "trades:" + lot["src"], lot["ref"], lot.get("estimated", False)])
    db.execute("delete from sales where source like ?", [OWNED])
    for kind, symbol, isin, when, qty, price, cur, src, ref in sold:
        db.execute("insert into sales (kind, symbol, isin, sold_on, quantity, price_per_unit, currency, source,"
                   " source_ref) values (?,?,?,?,?,?,?,?,?)", [kind, symbol, isin, when, _r(qty), _r(price), cur,
                                                               "trades:" + src, ref])
    result.lots = len(out)
    return result


def _estimated_lots(db, built: list) -> list:
    """Units Kite shows that the documents do not explain become one lot per holding, at Kite's average price and
    dated its snapshot, marked estimated. Tax uses it until a document arrives; the next rebuild finds the document's
    units already in `built` and adds less (or nothing), so a document always replaces the estimate. Units the documents
    show beyond Kite's are not touched here, and a holding in dollars (not Kite's) is skipped."""
    from stockpilot.book import kinds, positions
    snap = positions.last_kite_sync(db)
    if not snap:
        return _fidelity_gap_lots(db, built)
    have: dict = {}
    for lot in built:
        if not kinds.is_foreign({"kind": lot["kind"], "currency": lot["cur"]}):
            key = (kinds.canon(lot["kind"]), lot["isin"] or lot["symbol"])
            have[key] = have.get(key, 0.0) + lot["qty"] - lot["closed"]
    out = _fidelity_gap_lots(db, built)
    for (kind, ident), (symbol, qty, avg) in sorted(positions._kite(db).items(), key=lambda kv: str(kv[0])):
        gap = qty - have.get(("equity" if kind == "equity" else kind, ident), 0.0)
        if gap > 0.0005 and avg:
            isin = ident if ident != symbol or kind == "mf" else None
            out.append({"kind": "mf" if kind == "mf" else "stock", "symbol": symbol, "isin": isin, "on": snap.date(),
                        "qty": _r(gap), "cost": avg, "closed": 0.0, "cur": "INR", "src": "estimated",
                        "ref": f"estimated:{snap.date()}", "estimated": True})
    return out


def _statement_lots(db, built: list) -> list:
    """Fidelity's 'Current Shares' export (`fidelity_lots`) lists the lots as they stood on its day, in rupees. Those lots are
    real: they replace the documents' lots of that holding up to that day (a document dates a vest by its delivery, the
    statement by its vest day). Later vests stay from the documents; later sales close the statement's lots first in, first out.
    The cost per share is stored in dollars at the day's rate so `positions.held` gives back Fidelity's rupee cost exactly."""
    from stockpilot.sources import fx
    rows = db.execute("select as_of, symbol, isin, acquired_on, quantity, cost_basis_inr from fidelity_lots "
                      "where as_of = (select max(as_of) from fidelity_lots f where f.symbol = fidelity_lots.symbol) "
                      "order by symbol, acquired_on").fetchall()
    if not rows:
        return built
    rate_on = fx.rate_on(db)
    for symbol in sorted({r[1] for r in rows}):
        mine = [r for r in rows if r[1] == symbol]
        as_of, isin = mine[0][0], mine[0][2]
        is_mine = lambda l: l["kind"] == "rsu" and (l["symbol"] == symbol or l["isin"] == isin)
        built = [l for l in built if not (is_mine(l) and l["on"] <= as_of)]
        new = []
        for _, _, _, day, qty, basis in mine:
            rate = rate_on(day)
            if rate:
                new.append({"kind": "rsu", "symbol": symbol, "isin": isin, "on": day, "qty": qty, "cost": basis / qty / rate,
                            "closed": 0.0, "cur": "USD", "src": "fidelity_statement", "ref": f"statement:{as_of}:{day}"})
        for (qty,) in db.execute("select quantity from trades where kind = 'rsu' and side = 'sell' and status = 'confirmed' "
                                 "and (symbol = ? or isin = ?) and trade_date > ? order by trade_date, id", [symbol, isin, as_of]).fetchall():
            _sell(new, qty)
        built = built + new
    return built


def _fidelity_gap_lots(db, built: list) -> list:
    """Fidelity's latest Stock Plan statement says how many shares are held and what they cost in rupees. Vests after the
    last document are missing from `built`; the shares beyond it become one estimated lot dated the statement, priced so
    the whole holding costs what Fidelity says. A later vest document replaces it on the next rebuild."""
    from stockpilot.sources import fx
    row = db.execute("select as_of, symbol, isin, quantity, cost_basis_inr from fidelity_holdings "
                     "where as_of = (select max(as_of) from fidelity_holdings) order by symbol").fetchall()
    rate_on, out = fx.rate_on(db), []
    for as_of, symbol, isin, qty, basis in row:
        mine = [l for l in built if l["kind"] == "rsu" and (l["symbol"] == symbol or (isin and l["isin"] == isin))]
        have = sum(l["qty"] - l["closed"] for l in mine)
        gap, now_rate = qty - have, rate_on(as_of)
        if gap <= 0.0005 or not now_rate:
            continue
        paid = sum((l["qty"] - l["closed"]) * l["cost"] * (rate_on(l["on"]) or now_rate) for l in mine)
        rest = (basis - paid) if basis else 0.0
        cost_usd = rest / gap / now_rate if rest > 0 else None
        if cost_usd is None:
            continue
        out.append({"kind": "rsu", "symbol": symbol, "isin": isin, "on": as_of, "qty": _r(gap), "cost": cost_usd, "closed": 0.0,
                    "cur": "USD", "src": "estimated", "ref": f"estimated:fidelity:{as_of}", "estimated": True})
    return out


SERIES = re.compile(r"\s*-\s*(A|B|T|X|Z|BE|BZ|EQ|XT)$")   # series suffix on old contract notes: NBCC-A, JSL - A


def _company(symbol: str) -> str:
    return SERIES.sub("", symbol or "").strip()


def _one_company_one_key(rows, current: dict) -> list:
    """Stock trades that share a symbol (series suffix dropped) or an ISIN are one company: a rename keeps the ISIN
    (TWL became TITAGARH), a split can change it (Canara Bank 2024). Each company gets its latest symbol and the
    exchange's ISIN today (else its latest), so buys under old names meet sells under new ones."""
    parent: dict = {}

    def find(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for r in rows:
        if r[2] == "stock" and r[4]:
            parent[find(("i", r[4]))] = find(("s", _company(r[3])))
    name: dict = {}
    for r in rows:   # date order: the last symbol and ISIN seen win
        if r[2] == "stock":
            root = find(("s", _company(r[3])))
            sym = _company(r[3])
            name[root] = (sym, current.get(sym) or r[4] or name.get(root, (None, None))[1])
    out = []
    for r in rows:
        if r[2] == "stock":
            sym, isin = name[find(("s", _company(r[3])))]
            r = (*r[:3], sym, isin, *r[5:])
        out.append(r)
    return out


def _sell(open_lots, qty: float) -> float:
    for lot in open_lots:  # lots are in acquisition order: FIFO
        if qty <= 1e-9:
            break
        take = min(qty, lot["qty"] - lot["closed"])
        if take > 0:
            lot["closed"] += take
            qty -= take
    return qty


def _demerger_ready(action) -> bool:
    """A demerger counts once it carries the new company and the share of cost that moves: those numbers are
    tax, so they are entered from the company's published ratio, never guessed."""
    return action[3] == "demerger" and bool(action[6] and action[7]) and action[8] is not None and action[5]


def _apply_action(open_lots, action, ex_date, spawned):
    _, _, _, kind, num, den, new_isin, new_symbol, cost_fraction, price, source = action
    if kind == "split":  # num new shares for every `den` old; cost per share falls to match
        m = num / den
        for lot in open_lots:
            if lot["on"] < ex_date:
                lot["qty"] *= m
                lot["closed"] *= m
                lot["cost"] /= m
    elif kind == "bonus" and open_lots:  # num free shares per `den` held: one new lot, zero cost, dated ex-date
        held = sum(l["qty"] - l["closed"] for l in open_lots if l["on"] < ex_date)
        free = math.floor(held * num / den + 1e-9)
        if free > 0:
            base = open_lots[0]
            open_lots.append({**base, "on": ex_date, "qty": float(free), "cost": 0.0, "closed": 0.0,
                              "ref": f"bonus:{ex_date}"})
    elif kind == "demerger" and _demerger_ready(action):   # new shares for each lot, with its share of the cost
        for lot in open_lots:
            left = lot["qty"] - lot["closed"]
            if lot["on"] < ex_date and left > 1e-9:
                new_qty = left * num / den
                spawned.setdefault(new_symbol, []).append({
                    "kind": lot["kind"], "symbol": new_symbol, "isin": new_isin, "on": lot["on"], "qty": new_qty,
                    "cost": lot["cost"] * cost_fraction / (num / den), "closed": 0.0, "cur": lot["cur"],
                    "src": "demerger", "ref": f"demerger:{ex_date}"})
                lot["cost"] *= 1 - cost_fraction
    elif kind == "rights" and open_lots and price and source != "nse":
        # entered by the owner: shares taken up at `price`, dated the allotment day. NSE only says a rights issue
        # exists, not who subscribed: those units come from the documents or, failing that, from Kite (estimated lot)
        held = sum(l["qty"] - l["closed"] for l in open_lots if l["on"] < ex_date)
        new = math.floor(held * num / den + 1e-9)
        if new > 0:
            open_lots.append({**open_lots[0], "on": ex_date, "qty": float(new), "cost": float(price), "closed": 0.0,
                              "src": "rights", "ref": f"rights:{ex_date}"})


def holdings(db) -> list[Holding]:
    """What the lots say is held now: remaining quantity and weighted average cost per ISIN."""
    rows = db.execute(
        "select kind, symbol, isin, currency, sum(quantity - closed_quantity),"
        " sum((quantity - closed_quantity) * cost_per_unit) from lots"
        " group by kind, symbol, isin, currency having sum(quantity - closed_quantity) > 0.0000005"
        " order by symbol").fetchall()
    return [Holding(k, s, i, _r(q), _r(cost / q), c) for k, s, i, c, q, cost in rows]


def check_against_statement(db) -> tuple:
    """Lots against the latest CDSL statement, per ISIN: (as_of, [(isin, statement_qty, lots_qty)]) where they differ.
    Lots are wound back to the statement date by undoing later trades. Only Indian ISINs (the depository's view)."""
    as_of = db.execute("select max(as_of) from holding_statements").fetchone()[0]
    if as_of is None:
        return None, []
    held = dict(db.execute("select isin, quantity from holding_statements where as_of = ?", [as_of]).fetchall())
    ours = {h.isin: h.quantity for h in holdings(db) if h.isin and h.isin.startswith("IN")}
    for isin, net in db.execute("select isin, sum(case when side = 'buy' then quantity else -quantity end) from trades"
                                " where trade_date > ? and isin like 'IN%' group by isin", [as_of]).fetchall():
        ours[isin] = ours.get(isin, 0.0) - net
    gaps = [(isin, held.get(isin, 0.0), _r(ours.get(isin, 0.0))) for isin in sorted(set(held) | set(ours))
            if abs(held.get(isin, 0.0) - ours.get(isin, 0.0)) > 0.001]
    return as_of, gaps
