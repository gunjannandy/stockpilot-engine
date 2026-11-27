"""Who placed each trade: Dad in Kite, or a smallcase order. The tag sits on the trade (table `trade_tags`), never
on the holding: Kite can buy or sell any stock, so a holding is just a stock.

Sources, in order: the "Your smallcase order for <basket>" mail (every order of a rebalance: stock, side, quantity,
average price); then the rebalance-day signature for what is left; else Kite. `trade_tags` is derived: it is
rewritten from `trades` and `smallcase_orders` on every call, and `trades` is never changed.
NEEDS A REAL SAMPLE: the mail parser is built from the format in docs/status/grilling-2026-11-23.md item 5."""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

WINDOW_DAYS = 3          # the contract note can be dated a day or two after the order
PRICE_TOLERANCE = 0.01   # the mail shows an average price; the exchange fills can differ a little
SIGNATURE_STOCKS = 10    # a day with this many different stocks traded and no mail is taken as a rebalance

ROW = re.compile(r"^\s*(?P<name>[^|\t]+?)\s*(?:\||\t|\s{2,})\s*(?P<side>BUY|SELL)\s*(?:\||\t|\s{2,})\s*(?P<qty>[\d,]+(?:\.\d+)?)"
                 r"\s*(?:\||\t|\s{2,})\s*(?:Rs\.?|₹)?\s*(?P<price>[\d,]+(?:\.\d+)?)\s*$", re.I)
SUBJECT = re.compile(r"your smallcase order for\s+(.+)", re.I)
ORDER_DATE = re.compile(r"order date\s*:?\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", re.I)


@dataclass(frozen=True)
class Order:
    basket: str
    order_date: date
    name: str
    side: str
    quantity: float
    price: float
    source_ref: str = ""


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def parse_order_mail(body: str, subject: str, mail_date: date, source_ref: str = "") -> list[Order]:
    """Every order in one mail. Raises when the mail has none, so a changed layout shows up as a failed document."""
    m = SUBJECT.search(subject or "")
    basket = (m[1].strip() if m else "") or "smallcase"
    when = mail_date
    if d := ORDER_DATE.search(body):
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                when = datetime.strptime(re.sub(r"\s+", " ", d[1]), fmt).date()
                break
            except ValueError:
                pass
    orders = [Order(basket, when, re.sub(r"\s+", " ", r["name"]).strip(), r["side"].lower(), _num(r["qty"]),
                    _num(r["price"]), source_ref)
              for line in body.splitlines() if (r := ROW.match(line))]
    if not orders:
        raise ValueError("no orders found in the smallcase mail")
    return orders


def save_orders(db, orders) -> int:
    """Store orders (new ones only). The key counts repeats, so two equal orders in one mail both stay."""
    added = 0
    seen: dict[str, int] = {}
    for o in orders:
        base = f"{o.basket}|{o.order_date}|{o.name}|{o.side}|{o.quantity:g}|{o.price}"
        seen[base] = seen.get(base, 0) + 1
        key = f"{base}|{seen[base]}"
        if db.execute("select 1 from smallcase_orders where order_key = ?", [key]).fetchone():
            continue
        db.execute("insert into smallcase_orders values (?,?,?,?,?,?,?,?)",
                   [key, o.basket, o.order_date, o.name, o.side, o.quantity, o.price, o.source_ref])
        added += 1
    return added


def _squash(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").lower())


def tag_trades(db) -> dict:
    """Rewrite `trade_tags` for every confirmed buy and sell. Returns counts by how the tag was found."""
    trades = db.execute("select trade_key, symbol, side, trade_date, quantity, price from trades "
                        "where status = 'confirmed' and side in ('buy', 'sell') order by trade_date, id").fetchall()
    orders = db.execute("select basket, order_date, name, side, quantity, price from smallcase_orders "
                        "order by order_date, order_key").fetchall()
    tags: dict[str, tuple] = {}
    for basket, on, name, side, qty, price in orders:
        best = None
        for key, symbol, t_side, t_day, t_qty, t_price in trades:
            if key in tags or t_side != side or abs(t_qty - qty) > 1e-6 or abs((t_day - on).days) > WINDOW_DAYS:
                continue
            if t_price is None or abs(t_price - price) > PRICE_TOLERANCE * price:
                continue
            same_name = _squash(symbol) and _squash(symbol) in _squash(name)
            rank = (0 if same_name else 1, abs(t_price - price), abs((t_day - on).days))
            if best is None or rank < best[0]:
                best = (rank, key)
        if best:
            tags[best[1]] = ("smallcase", basket, "mail")
    order_days = [o[1] for o in orders]
    by_day: dict[date, set] = {}
    for key, symbol, _, day, _, _ in trades:
        if key not in tags:
            by_day.setdefault(day, set()).add(symbol)
    rebalance = {d for d, symbols in by_day.items() if len(symbols) >= SIGNATURE_STOCKS
                 and not any(abs((d - o).days) <= WINDOW_DAYS for o in order_days)}
    for key, _, _, day, _, _ in trades:
        if key not in tags:
            tags[key] = ("smallcase", None, "signature") if day in rebalance else ("kite", None, "default")
    db.execute("delete from trade_tags")
    for k, v in tags.items():
        db.execute("insert into trade_tags values (?,?,?,?)", [k, *v])
    counts: dict[str, int] = {}
    for _, _, how in tags.values():
        counts[how] = counts.get(how, 0) + 1
    return counts
