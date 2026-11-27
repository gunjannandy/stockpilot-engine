"""The RSU bridge: Fidelity vests and sales (`fidelity_events`, parsed from the owner's documents) become trades of one US
holding, ServiceNow, so the lots, `positions.held`, the portfolio page and Schedule FA all see it.

- A vest is the net shares deposited, at the vest-day fair market value, in dollars. The rupee cost of each lot is that
  price times the rate of the vest day (`positions.held` does the multiplication, lot by lot).
- Grant and 5-for-1 split rows in the documents are not vests and never reach here (the parser skips them).
- Documents speak in the units of their day, so a pre-split vest is in old shares. The split is stored as a corporate
  action (once) and `lots.rebuild` scales the old lots, as it does for an Indian split.
- Two documents often show one vest (the year-end report has the vest day, a statement the delivery a few days later):
  the year-end row wins. A vest the email route stored already is not stored again."""
from datetime import date

from stockpilot.trades import lots
from stockpilot.trades.fidelity import NOW_ISIN
from stockpilot.trades.fidelity_docs import NEAR_DAYS

SYMBOL = "NOW"
SPLIT_EX = date(2025, 12, 18)      # first day ServiceNow traded 5-for-1 (distribution after the close of 17 Dec 2025)
SPLIT_RATIO = 5


UNIQUE = ("select distinct event_date, kind, grant_id, quantity, net_quantity, price_usd, amount_usd, acquired_on "
          "from fidelity_events")      # the same report saved twice in Drive is one set of events


def _vests(db) -> list[tuple]:
    """(day, net shares, price) per vest. A statement row counts only where no year-end row sits near it, and takes the
    day a sale says the shares were acquired when one is just before it (a statement dates a vest by its delivery)."""
    rows = db.execute(f"select event_date, sum(coalesce(net_quantity, quantity)), max(price_usd), grant_id is not null "
                      f"from ({UNIQUE}) where kind = 'vest' and price_usd is not null "
                      f"group by event_date, grant_id is not null order by event_date").fetchall()
    acquired = [d for (d,) in db.execute(f"select distinct acquired_on from ({UNIQUE}) where kind = 'sale' "
                                         f"and acquired_on is not null").fetchall()]
    full = [(d, q, p) for d, q, p, grant in rows if grant]
    extra = []
    for d, q, p, grant in rows:
        if grant or any(abs((d - f[0]).days) <= NEAR_DAYS for f in full):
            continue
        before = [a for a in acquired if 0 <= (d - a).days <= NEAR_DAYS]
        extra.append((min(before) if before else d, q, p))
    return sorted(full + extra)


def _sales(db) -> list[tuple]:
    """(day, shares, price) per sale. The transaction summary has the trade date; a statement sale (its date is the
    settlement day) counts only where the summary has none near it."""
    rows = db.execute(f"select event_date, sum(quantity), sum(coalesce(amount_usd, quantity * price_usd)) / sum(quantity), "
                      f"acquired_on is not null from ({UNIQUE}) where kind = 'sale' and price_usd is not null "
                      f"group by event_date, acquired_on is not null order by event_date").fetchall()
    exact = [(d, q, p) for d, q, p, summary in rows if summary]
    extra = [(d, q, p) for d, q, p, summary in rows if not summary
             and not any(abs((d - e[0]).days) <= NEAR_DAYS and abs(q - e[1]) < 0.01 for e in exact)]
    return sorted(exact + extra)


def _stored(db) -> list[tuple]:
    """Trades of this holding that came from somewhere other than this bridge (the Fidelity email route)."""
    return db.execute("select side, trade_date, quantity from trades where (symbol = ? or isin = ?) and kind = 'rsu' "
                      "and source <> 'fidelity_docs'", [SYMBOL, NOW_ISIN]).fetchall()


def _store_split(db) -> None:
    db.execute("insert or ignore into corporate_actions (symbol, isin, ex_date, kind, numerator, denominator, subject, source) "
               "values (?, ?, ?, 'split', ?, 1, 'ServiceNow 5-for-1 stock split', 'fidelity')",
               [SYMBOL, NOW_ISIN, SPLIT_EX, SPLIT_RATIO])


def bridge(db) -> int:
    """Store the vests and sales of `fidelity_events` as trades and return how many were new. Idempotent."""
    others = _stored(db)
    wanted = [("vest", d, q, p) for d, q, p in _vests(db)] + [("sell", d, q, p) for d, q, p in _sales(db)]
    trades = []
    for side, day, qty, price in wanted:
        if any(s == side and abs((d - day).days) <= NEAR_DAYS and abs(q - qty) < 0.01 for s, d, q in others):
            continue
        key = f"fidelity:vest:{day}" if side == "vest" else f"fidelity:sale:{day}:{qty:g}"
        trades.append(lots.Trade("fidelity_docs", key, "rsu", SYMBOL, NOW_ISIN, side, day, qty, price, "USD", trade_key=key))
    if wanted:
        _store_split(db)
    return lots.save_trades(db, trades)
