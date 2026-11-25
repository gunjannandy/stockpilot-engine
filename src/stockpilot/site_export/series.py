"""Price series for many stocks, a chunk at a time (the VM has 1 GB), with the numbers every screen needs."""
from datetime import timedelta

from stockpilot.analysis import analytics

CHUNK = 120
DAILY = 250            # trading days kept day by day
WEEKLY_STEP = 5        # older days keep one point in five
YEARS = 5
DAY_RANGE = 252        # one year of trading days


def _rolling(closes, n):
    out, total = [], 0.0
    for i, c in enumerate(closes):
        total += c
        if i >= n:
            total -= closes[i - n]
        out.append(round(total / n, 2) if i >= n - 1 else None)
    return out


def chunks(db, exchanges: dict, as_of):
    """Yield (symbol, rows) with rows = [(date, adjusted close, volume)] oldest first, for each symbol with any price.
    `exchanges` maps symbol to the exchange its prices are on."""
    since = as_of - timedelta(days=365 * YEARS + 10)
    for exchange in sorted(set(exchanges.values())):
        symbols = sorted(s for s, x in exchanges.items() if x == exchange)
        for i in range(0, len(symbols), CHUNK):
            part = symbols[i:i + CHUNK]
            closes = analytics.adjusted_closes_many(db, part, since, exchange)
            vols: dict = {}
            for sym, day, vol in db.execute("select symbol, date, volume from prices where exchange = ? and date >= ? and date <= ? "
                                            "and symbol in (select unnest(?))", [exchange, since, as_of, part]).fetchall():
                vols[(sym, day)] = vol
            for sym in part:
                yield sym, [(d, c, vols.get((sym, d))) for d, c in closes.get(sym, []) if d <= as_of]


def history_file(symbol, rows, as_of) -> dict:
    """Day by day for the last DAILY trading days (close, volume, 50- and 200-day averages) and, before them, one point in
    five for the long ranges. Older averages are not needed: the page draws them only on the daily part."""
    closes = [c for _, c, _ in rows]
    d50, d200 = _rolling(closes, 50), _rolling(closes, 200)
    cut = max(0, len(rows) - DAILY)
    older = list(range(cut - 1, -1, -WEEKLY_STEP))[::-1]
    return {"symbol": symbol, "as_of": str(as_of),
            "dates": [str(rows[i][0]) for i in range(cut, len(rows))],
            "close": [round(closes[i], 2) for i in range(cut, len(rows))],
            "volume": [rows[i][2] or 0 for i in range(cut, len(rows))],
            "dma50": d50[cut:], "dma200": d200[cut:],
            "older": {"dates": [str(rows[i][0]) for i in older], "close": [round(closes[i], 2) for i in older]}}
