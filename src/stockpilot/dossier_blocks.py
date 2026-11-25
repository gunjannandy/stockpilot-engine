"""The three blocks the analyst reasons from, worked out by code from data on file (lane E, v10 decision 8):

  history   company history: years on record, up to 10 financial years of sales and profit, whether profit kept rising,
            and how the price behaved in past falls of 20% or more (how deep, how long, what the market did)
  gravity   market gravity: size and its rank among the stocks we follow, who owns it, how easily it trades, its place
            against its sector
  news      the month: the biggest one-day moves of the price with what the company said around them, and how its sector
            and the market moved

A block with nothing to say is left out. Code states facts; the model writes the view. No block holds a recommendation."""
from datetime import date, timedelta

from stockpilot import readiness
from stockpilot.analysis import analytics
from stockpilot.sources import filings

YEARS = 10
FALL = 0.20                     # a fall counts from this much below the earlier high
TOP_FALLS = 3
MOVE = 0.04                     # a one-day move this big is worth explaining
TOP_MOVES = 3
MONTH_DAYS = 30
QUARTER_MONTHS = {6, 9, 12, 3}


def _crore(x):
    return None if x is None else round(x / 1e7, 1)


def _fy(period_end: date) -> int:
    return period_end.year + 1 if period_end.month >= 4 else period_end.year


def _yearly(db, symbol: str, day: date) -> list[dict]:
    if not readiness.has_table(db, "quarterly"):
        return []
    rows = filings.history(db, symbol, day, 4 * (YEARS + 1))
    years: dict[int, dict] = {}
    for r in rows:
        if r["period_end"].month in QUARTER_MONTHS:
            years.setdefault(_fy(r["period_end"]), {})[r["period_end"].month] = r
    out = []
    for fy in sorted((y for y, q in years.items() if set(q) == QUARTER_MONTHS), reverse=True)[:YEARS]:
        q = years[fy].values()
        if any(x["net_profit"] is None for x in q):
            continue
        out.append({"fy": f"FY{fy}", "revenue_cr": _crore(sum(x["revenue"] or 0 for x in q)),
                    "profit_cr": _crore(sum(x["net_profit"] for x in q))})
    return out


def _weekly(rows: list) -> list:
    """The last close of each calendar week, oldest first."""
    out: dict = {}
    for d, close in rows:
        out[d.isocalendar()[:2]] = (d, close)
    return list(out.values())


def _index_move(db, name: str, start: date, end: date):
    """The index's return between two dates, or None."""
    rows = db.execute("select date, close from index_levels where name = ? and date <= ? and date >= ? order by date",
                      [name, end, start - timedelta(days=7)]).fetchall()
    old = [c for d, c in rows if d <= start]
    if not rows or not old or not old[-1]:
        return None
    return rows[-1][1] / old[-1] - 1


def _falls(db, symbol: str, day: date) -> list[dict]:
    weeks = _weekly(analytics.adjusted_closes(db, symbol, day - timedelta(days=365 * YEARS + 10), "NSE")
                    or analytics.adjusted_closes(db, symbol, day - timedelta(days=365 * YEARS + 10), "BSE"))
    weeks = [(d, c) for d, c in weeks if d <= day and c]
    found, peak_i, trough_i, deep = [], 0, 0, False
    for i, (_, close) in enumerate(weeks):
        if close >= weeks[peak_i][1]:
            if deep:
                found.append((peak_i, trough_i, i))
            peak_i, trough_i, deep = i, i, False
            continue
        if close < weeks[trough_i][1] or trough_i < peak_i:
            trough_i = i
        if close / weeks[peak_i][1] - 1 <= -FALL:
            deep = True
    if deep:
        found.append((peak_i, trough_i, None))
    out = []
    for peak_i, trough_i, back_i in found:
        (pd_, pc), (td, tc) = weeks[peak_i], weeks[trough_i]
        row = {"from": f"{pd_:%Y-%m}", "to": f"{td:%Y-%m}", "fall_pct": round(100 * (tc / pc - 1)),
               "recovered_after_weeks": None if back_i is None else back_i - peak_i}
        market = _index_move(db, "Nifty 50", pd_, td)
        if market is not None:
            row["nifty_pct"] = round(100 * market)
        out.append(row)
    return sorted(out, key=lambda f: f["fall_pct"])[:TOP_FALLS]


def history(db, symbol: str, day: date) -> dict:
    out: dict = {}
    first = db.execute("select min(date) from prices where symbol = ? and date <= ?", [symbol, day]).fetchone()[0]
    if first:
        out["years_on_record"] = round((day - first).days / 365.25, 1)
    yearly = _yearly(db, symbol, day)
    if yearly:
        out["yearly"] = yearly
        pairs = [(a["profit_cr"], b["profit_cr"]) for a, b in zip(yearly, yearly[1:])][:4]     # newest year first
        if pairs:
            rose = sum(new > old for new, old in pairs)
            out["profit_trend"] = f"Profit rose in {rose} of the last {len(pairs)} years."
    if falls := _falls(db, symbol, day):
        out["falls"] = falls
    return out


def size_ranks(db, day: date) -> dict:
    """symbol -> (market cap in rupees, rank, how many), from the newest market-cap snapshot each stock has."""
    rows = db.execute("select symbol, arg_max(value, as_of) from fundamentals where metric = 'market_cap' and as_of <= ? "
                      "and value > 0 group by symbol", [day + timedelta(days=7)]).fetchall()
    ranked = sorted(rows, key=lambda r: -r[1])
    return {s: (cap, i + 1, len(ranked)) for i, (s, cap) in enumerate(ranked)}


def gravity(db, symbol: str, day: date, price: dict, industry, ranks: dict) -> dict:
    out: dict = {}
    if symbol in ranks:
        cap, rank, total = ranks[symbol]
        out["market_cap_cr"] = round(cap / 1e7)
        out["size_rank"] = f"{rank} of {total} stocks we follow"
    held = db.execute("select arg_max(value, as_of) from fundamentals where symbol = ? and metric = 'insiders_pct' "
                      "and as_of <= ?", [symbol, day + timedelta(days=7)]).fetchone()[0]
    if held is not None:
        out["owners"] = {"insiders_pct": round(100 * held, 1)}
    liquidity = (price or {}).get("liquidity_cr")
    if liquidity is not None:
        tier = "very liquid" if liquidity >= 100 else "liquid" if liquidity >= 10 else "thin"
        out["liquidity"] = f"{tier} (about ₹{liquidity:,.0f} crore traded a day)"
    if industry and (price or {}).get("vs_sector_3m") is not None:
        out["sector"] = {"name": industry, "vs_sector_3m_points": round(100 * price["vs_sector_3m"], 1)}
    return out


def news(db, symbol: str, day: date, announcements: list, headlines: list, sector_index: str | None = None) -> dict:
    out: dict = {}
    rows = analytics.adjusted_closes(db, symbol, day - timedelta(days=MONTH_DAYS + 10), "NSE")
    moves = []
    for (_, prev), (d, close) in zip(rows, rows[1:]):
        if d > day - timedelta(days=MONTH_DAYS) and prev and abs(close / prev - 1) >= MOVE:
            said = [i["id"] for i in announcements + headlines if str(d - timedelta(days=1)) <= i["date"] <= str(d)]
            moves.append({"date": str(d), "pct": round(100 * (close / prev - 1), 1), "said": said})
    if moves:
        out["moves"] = sorted(moves, key=lambda m: -abs(m["pct"]))[:TOP_MOVES]
    start = day - timedelta(days=MONTH_DAYS)
    if sector_index and (s := _index_move(db, sector_index, start, day)) is not None:
        out["sector_1m_pct"] = round(100 * s, 1)
    if (m := _index_move(db, "Nifty 50", start, day)) is not None:
        out["market_1m_pct"] = round(100 * m, 1)
    return out
