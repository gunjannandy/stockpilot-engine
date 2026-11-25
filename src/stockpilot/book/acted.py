"""Which calls the owners acted on. A buy of a stock within 5 trading days after a buy call on it (a sell after a
sell or trim call likewise), seen in contract notes or in Kite trades, sets `calls.acted_on` to the trade's date.
It feeds his own record and the month's budget left; it never reaches a forecast. Run after every document sync and
Kite sync; it is safe to repeat and never moves a date already set."""
import json
from datetime import date, datetime, timedelta

WINDOW = 5   # trading days after the call

_CALL_SIDE = {"buy": "buy", "add": "buy", "sell": "sell", "trim": "sell"}


def _trading_days_between(db, first: date, last: date) -> int:
    """Trading days in (first, last]: weekdays that are not NSE holidays."""
    holidays = {r[0] for r in db.execute("select date from holidays where date > ? and date <= ?", [first, last]).fetchall()}
    n, d = 0, first
    while d < last:
        d += timedelta(days=1)
        if d.weekday() < 5 and d not in holidays:
            n += 1
    return n


def _kite_trades(db) -> set[tuple[str, str, date]]:
    """(symbol, side, day) from the most recent Kite syncs; Kite lists only the day's trades, so read every stored sync."""
    out = set()
    for (raw,) in db.execute("select trades from kite_syncs where trades is not null").fetchall():
        try:
            rows = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            continue
        for t in rows or []:
            when = t.get("fill_timestamp") or t.get("order_timestamp") or t.get("exchange_timestamp")
            side = str(t.get("transaction_type", "")).lower()
            if t.get("tradingsymbol") and side in ("buy", "sell") and when:
                try:
                    out.add((str(t["tradingsymbol"]).upper(), side, datetime.fromisoformat(str(when)[:19]).date()))
                except ValueError:
                    continue
    return out


def _trades(db) -> dict[tuple[str, str], list[date]]:
    found = {(s, side, d) for s, side, d in db.execute(
        "select symbol, lower(side), trade_date from trades where status = 'confirmed' and lower(side) in ('buy', 'sell')").fetchall()}
    found |= _kite_trades(db)
    by: dict[tuple[str, str], list[date]] = {}
    for symbol, side, day in sorted(found, key=lambda x: x[2]):
        by.setdefault((symbol, side), []).append(day)
    return by


def mark(db) -> int:
    """Set `acted_on` on every open call that a matching trade followed within the window; returns how many."""
    trades = _trades(db)
    open_calls = db.execute("select id, symbol, made_on, coalesce(section, action) from calls "
                            "where acted_on is null and made_on is not null order by id").fetchall()
    n = 0
    for call_id, symbol, made_on, kind in open_calls:
        side = _CALL_SIDE.get(kind)
        if not side:
            continue
        for day in trades.get((symbol, side), []):
            if day > made_on and _trading_days_between(db, made_on, day) <= WINDOW:
                db.execute("update calls set acted_on = ? where id = ?", [day, call_id])
                n += 1
                break
    return n
