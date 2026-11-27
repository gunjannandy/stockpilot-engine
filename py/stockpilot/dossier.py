"""The dossier: one stock's facts, worked out by code, small enough (about 600-900 tokens as compact JSON) that 35 of them
fit one model call. `build` is per stock; `market` is the one block about the whole market; `context` holds what both
share so it is worked out once an evening. A source table another lane has not built yet is simply left out."""
import json
from dataclasses import dataclass, field
from datetime import date, timedelta
from statistics import median

from stockpilot import costs, dossier_blocks as blocks, readiness

from stockpilot.analysis import analytics, backtest
from stockpilot.book.positions import Position

WEEKS = 52
ATR_DAYS = 14
SWING_WINDOW = 5            # a swing low or high beats the 5 days either side
SWING_LOOKBACK = 130        # trading days of highs and lows searched for support and resistance
VOLUME_DAYS = 20
NEWS_DAYS = 30          # the last month
DEAL_DAYS = 30
MAX_ITEMS = 5
MAX_LOTS = 6
THREE_MONTHS = 63           # trading days
FUND_KEYS = ["pe", "pb", "roe", "roce", "debt_to_equity", "profit_cagr_3y", "revenue_cagr_3y"]
HORIZON_DAYS = 91


@dataclass
class Context:
    """What every dossier of one evening shares. All parts are optional."""
    day: date
    rates: dict = field(default_factory=dict)          # (factor, bucket, regime) -> {n, hit_rate}
    regime: str = "unknown"
    candidates: dict = field(default_factory=dict)     # symbol -> the screen's row
    positions: dict = field(default_factory=dict)      # symbol -> Position (equity)
    portfolio_value: float = 0.0
    sector_index: dict = field(default_factory=dict)   # industry -> index name
    medians: dict = field(default_factory=dict)        # industry -> median P/E
    sector_returns: dict = field(default_factory=dict)  # index name -> 3-month return
    median_vol: float | None = None                    # median 1-year volatility across the screen's stocks tonight
    sizes: dict | None = None                          # symbol -> (market cap, rank, how many); worked out once an evening


def _r(x, digits=None):
    if x is None:
        return None
    if digits is None:
        digits = 2 if abs(x) < 100 else 1
    return round(x, digits)


def regime_of(health: dict) -> str:
    up = health.get("nifty_above_200dma")
    return "unknown" if up is None else ("nifty_up" if up else "nifty_down")


def load_rates(db) -> dict:
    """The 40-bucket table as {(momentum, regime, vol, liquidity): {n, hit_rate}}, with the older momentum x regime table
    under {("momentum", bucket, regime): ...} for a database the new backtest has not run on yet."""
    rates = {(m, r, v, l): {"n": n, "hit_rate": h} for m, r, v, l, n, h in db.execute(
        "select momentum, regime, vol, liquidity, n, hit_rate from base_rate_buckets where horizon_days = ?",
        [HORIZON_DAYS]).fetchall()}
    for f, b, r, n, h in db.execute("select factor, bucket, regime, n, hit_rate from base_rates where horizon_days = ?",
                                    [HORIZON_DAYS]).fetchall():
        rates[(f, b, r)] = {"n": n, "hit_rate": h}
    return rates


def median_vol(candidates: dict) -> float | None:
    """The median 1-year volatility across the screen's stocks tonight: the line between calm and jumpy."""
    vols = [c["metrics"]["vol_1y"] for c in candidates.values() if (c.get("metrics") or {}).get("vol_1y") is not None]
    return median(vols) if vols else None


def base_rate(rates: dict, candidate: dict | None, regime: str, median_vol_1y: float | None = None) -> dict:
    """How often stocks like this one beat the Nifty by more than the hurdle: its momentum bucket and regime, its volatility
    against the median (calm or jumpy) and its liquidity (large or small). Falls back to the momentum x regime table when
    the 40-bucket one is empty. No screen row or no table entry: 50%, sample size 0."""
    if candidate:
        bucket = min(4, int(candidate["scores"]["momentum"] * 5))
        m = candidate.get("metrics") or {}
        calm, size = backtest.cut_of(m.get("vol_1y"), median_vol_1y, m.get("adv_3m_cr"))
        hit = rates.get((bucket, regime, calm, size)) or rates.get(("momentum", bucket, regime))
        if hit:
            return {"rate": round(hit["hit_rate"], 3), "n": hit["n"]}
    return {"rate": 0.5, "n": 0}


def _index_return(db, name: str, day: date) -> float | None:
    rows = db.execute("select close from index_levels where name = ? and date <= ? order by date desc limit ?",
                      [name, day, THREE_MONTHS + 1]).fetchall()
    return rows[0][0] / rows[-1][0] - 1 if len(rows) == THREE_MONTHS + 1 else None


def context(db, day: date, screen_result: dict | None = None, held: list[Position] | None = None,
            sector_index: dict | None = None) -> Context:
    ctx = Context(day, rates=load_rates(db), sector_index=dict(sector_index or {}))
    if screen_result:
        ctx.regime = regime_of(screen_result["health"])
        ctx.candidates = {c["symbol"]: c for c in screen_result["candidates"]}
        ctx.median_vol = median_vol(ctx.candidates)
    for p in held or []:
        if p.kind == "equity":
            ctx.positions[p.symbol] = p
    ctx.portfolio_value = sum(p.value for p in held or [] if p.kind == "equity")   # stocks only: the conservative base for the 8% cap
    ctx.medians = dict(db.execute("""
        select s.industry, median(f.pe) from (select symbol, arg_max(value, as_of) pe from fundamentals
        where metric = 'pe' and as_of <= ? group by symbol) f join stocks s using (symbol)
        where f.pe > 0 and s.industry is not null group by s.industry""",
        [day + timedelta(days=readiness.FUNDAMENTALS_MAX_AHEAD_DAYS)]).fetchall())
    for name in set(ctx.sector_index.values()):
        ctx.sector_returns[name] = _index_return(db, name, day)
    ctx.sizes = blocks.size_ranks(db, day)
    return ctx


# ---- prices ---------------------------------------------------------------------------------------------

def _daily(db, symbol: str, day: date):
    """Split-adjusted daily rows (date, high, low, close, volume, value), oldest first; NSE first, else BSE, else NYSE (a US
    share the owners hold, in dollars: lane R)."""
    since = day - timedelta(days=400)
    for exchange in ("NSE", "BSE", "NYSE"):
        sql = analytics.ADJUSTED_SQL.format(symbol_filter="and symbol = $symbol and exchange = $exchange")
        rows = db.execute(f"""
            select p.date, p.high * a.adj_close / p.close, p.low * a.adj_close / p.close, a.adj_close, p.volume, p.value
            from ({sql}) a join prices p on p.symbol = a.symbol and p.exchange = a.exchange and p.date = a.date
            where p.date <= $day and p.close > 0 order by p.date""",
            {"since": since, "symbol": symbol, "exchange": exchange, "day": day}).fetchall()
        if rows:
            return rows
    return []


def atr(highs, lows, closes, n: int = ATR_DAYS) -> float | None:
    """The average true range of the last n days: the typical daily move in rupees."""
    if len(closes) < n + 1:
        return None
    tr = [max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1]))
          for i in range(len(closes) - n, len(closes))]
    return sum(tr) / n


def swing_levels(highs, lows, close: float, atr: float | None):
    """Two supports (recent swing lows below the close, nearest first) and two resistances (swing highs above it).
    Levels closer together than half a daily move count as one."""
    highs, lows = highs[-SWING_LOOKBACK:], lows[-SWING_LOOKBACK:]
    k, apart = SWING_WINDOW, 0.5 * (atr or 0)
    swing_lows = [lows[i] for i in range(k, len(lows) - k) if lows[i] == min(lows[i - k:i + k + 1])]
    swing_highs = [highs[i] for i in range(k, len(highs) - k) if highs[i] == max(highs[i - k:i + k + 1])]

    def pick(levels, nearest_first):
        out = []
        for level in sorted(set(levels), reverse=nearest_first is True):
            if not out or abs(level - out[-1]) >= apart:
                out.append(level)
        return out[:2]
    support = pick([x for x in swing_lows if x < close], True)
    resistance = pick([x for x in swing_highs if x > close], False)
    return [_r(x) for x in support], [_r(x) for x in resistance]


def _weekly(rows, day: date) -> list[float]:
    by_week: dict[int, float] = {}
    for d, _h, _l, c, _v, _val in rows:
        weeks_ago = (day - d).days // 7
        if weeks_ago < WEEKS:
            by_week[weeks_ago] = c            # rows are oldest first, so the week's last close wins
    return [_r(by_week[w]) for w in sorted(by_week, reverse=True)]


def _price_block(db, rows, day: date, symbol: str, industry, ctx: Context) -> dict:
    highs, lows, closes = [r[1] for r in rows], [r[2] for r in rows], [r[3] for r in rows]
    a = atr(highs, lows, closes)
    close = closes[-1]
    year = closes[-252:]
    support, resistance = swing_levels(highs, lows, close, a)
    vols = [r[4] for r in rows[-VOLUME_DAYS - 1:-1]]
    values = [r[5] for r in rows[-63:] if r[5] is not None]      # a US share has no traded value in rupees
    block = {"close": _r(close), "high_52w": _r(max(year)), "low_52w": _r(min(year)),
             "atr": _r(a), "atr_pct": round(a / close, 4) if a else None, "support": support, "resistance": resistance,
             "vol_vs_20d": round(rows[-1][4] / (sum(vols) / len(vols)), 2) if vols and sum(vols) else None,
             "liquidity_cr": round(sum(values) / len(values) / 1e7, 1) if values else None}
    if len(closes) > THREE_MONTHS:
        block["ret_3m"] = round(close / closes[-THREE_MONTHS - 1] - 1, 4)
        sector = ctx.sector_returns.get(ctx.sector_index.get(industry))
        if sector is not None:
            block["sector_3m"] = round(sector, 4)
            block["vs_sector_3m"] = round(block["ret_3m"] - sector, 4)
    return block


# ---- the other blocks -----------------------------------------------------------------------------------

def _fundamentals(db, symbol: str, day: date, industry, ctx: Context) -> dict:
    ahead = day + timedelta(days=readiness.FUNDAMENTALS_MAX_AHEAD_DAYS)
    rows = db.execute("select as_of, metric, value from fundamentals where symbol = ? and as_of <= ? "
                      "and metric in (" + ",".join("?" * len(FUND_KEYS)) + ") order by as_of",
                      [symbol, ahead, *FUND_KEYS]).fetchall()
    snaps: dict[date, dict] = {}
    for as_of, metric, value in rows:
        snaps.setdefault(as_of, {})[metric] = _r(value, 3)
    if not snaps:
        return {}
    dates = sorted(snaps)
    latest = {"as_of": str(dates[-1]), **snaps[dates[-1]]}
    earlier = [{"as_of": str(d), **snaps[d]} for d in dates[:-1][-6:]]
    out = {"fundamentals": latest, "earlier": earlier}
    view = {}
    pe = snaps[dates[-1]].get("pe")
    own = [snaps[d]["pe"] for d in dates[:-1] if "pe" in snaps[d]]
    if pe and own:
        view["vs_own"] = f"higher than {sum(pe > o for o in own)} of {len(own)} earlier readings"
    if pe and ctx.medians.get(industry):
        view["industry_median"] = _r(ctx.medians[industry])
    if view:
        out["pe_view"] = view
    return out


def _delivery(db, symbol: str, day: date) -> dict | None:
    if not readiness.has_table(db, "delivery"):
        return None
    rows = db.execute("select date, deliv_pct from delivery where symbol = ? and series in ('EQ', 'BE') and date <= ? "
                      "and deliv_pct is not null order by date desc limit 21", [symbol, day]).fetchall()
    if not rows or rows[0][0] != day:
        return None
    rest = [p for _, p in rows[1:]]
    return {"today": _r(rows[0][1], 1), "avg_20d": _r(sum(rest) / len(rest), 1) if rest else None}


def _short(text: str, n: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1] + "…"


def _news(db, symbol: str, day: date) -> tuple[list, list]:
    since = day - timedelta(days=NEWS_DAYS)
    ann = [{"date": str(a)[:10], "subject": _short(s, 90)} for a, s in db.execute(
        "select announced_at, subject from announcements where symbol = ? and announced_at >= ? and announced_at < ? "
        "order by announced_at desc limit ?", [symbol, since, day + timedelta(days=1), MAX_ITEMS]).fetchall()]
    heads = []
    if readiness.has_table(db, "headlines"):
        heads = [{"date": str(a)[:10], "title": _short(t, 100), "source": s} for a, t, s in db.execute(
            "select published_at, title, source from headlines where symbol = ? and published_at >= ? and published_at < ? "
            "order by published_at desc limit ?", [symbol, since, day + timedelta(days=1), MAX_ITEMS]).fetchall()]
    n = 0
    for item in ann + heads:        # one numbering across both, so `news_used` can cite any of them
        n += 1
        item["id"] = f"{symbol}-{n}"
    return ann, heads


QUARTERS = 8


def year_ago(rows: list[dict]) -> dict | None:
    """The quarter a year before the newest of `rows` (newest first), within 20 days of exactly a year."""
    return next((r for r in rows[1:] if abs((rows[0]["period_end"] - r["period_end"]).days - 365) <= 20), None) if rows else None


def eps_adjustments(db, symbol: str, day: date) -> list[tuple[date, float]]:
    """(ex-date, share-count multiplier) for each split and bonus in effect on `day`, the same factors the price
    adjustment uses: a split of a:b is a/b, a bonus of a:b is (a+b)/b."""
    return [(ex, n / d if kind == "split" else (n + d) / d) for ex, kind, n, d in db.execute(
        "select ex_date, kind, numerator, denominator from corporate_actions where symbol = ? and kind in ('split', 'bonus') "
        "and numerator > 0 and denominator > 0 and ex_date <= ?", [symbol, day]).fetchall()]


def adjusted_eps(row: dict, actions: list[tuple[date, float]]) -> float | None:
    """EPS on today's share count. A quarter filed before an ex-date counts the old, smaller share count, so each such
    split or bonus divides it; a quarter filed after already counts the new shares."""
    if row["eps"] is None:
        return None
    filed = row["filed_at"].date() if hasattr(row["filed_at"], "date") else row["filed_at"]
    factor = 1.0
    for ex, mult in actions:
        if ex > filed:
            factor *= mult
    return row["eps"] / factor


def _quarters(db, symbol: str, day: date) -> dict:
    """Eight quarters of revenue (₹ crore), net profit (₹ crore) and EPS (split- and bonus-adjusted), newest first, and the
    latest quarter's growth on the same quarter a year earlier. Left out when there is nothing filed."""
    if not readiness.has_table(db, "quarterly"):
        return {}
    from stockpilot.sources import filings
    rows = filings.history(db, symbol, day, QUARTERS)
    if not rows:
        return {}
    actions = eps_adjustments(db, symbol, day)
    eps = [adjusted_eps(r, actions) for r in rows]
    cr = lambda x: None if x is None else round(x / 1e7, 1)      # noqa: E731
    out_rows = [{"period": str(r["period_end"]), "revenue": cr(r["revenue"]), "net_profit": cr(r["net_profit"]),
                 "eps": None if e is None else round(e, 2)} for r, e in zip(rows, eps)]
    base = year_ago(rows)
    yoy = {}
    if base:
        i = rows.index(base)
        for key, new, old in (("revenue", rows[0]["revenue"], base["revenue"]), ("net_profit", rows[0]["net_profit"], base["net_profit"]),
                              ("eps", eps[0], eps[i])):
            yoy[key] = round(new / old - 1, 3) if new is not None and old and old > 0 else None
    return {"quarters": {"rows": out_rows, "yoy": yoy}}


def _deals(db, symbol: str, day: date) -> list[str]:
    if not readiness.has_table(db, "deals"):
        return []
    out = []
    for d, kind, client, side, qty, price in db.execute(
            "select date, kind, client, side, quantity, price from deals where symbol = ? and date >= ? and date <= ? "
            "order by date desc limit 4", [symbol, day - timedelta(days=DEAL_DAYS), day]).fetchall():
        amount = f"{qty / 1e5:.1f} lakh" if qty >= 1e5 else f"{qty:,.0f}"
        out.append(f"{kind} {str(side).upper()} {amount} @{price:g} by {_short(client, 28)} ({d:%d %b})")
    return out


def _results_on(db, symbol: str, day: date) -> str | None:
    if not readiness.has_table(db, "results_calendar"):
        return None
    row = db.execute("select min(date) from results_calendar where symbol = ? and date >= ?", [symbol, day]).fetchone()
    return str(row[0]) if row and row[0] else None


def _flag(db, symbol: str, day: date) -> str | None:
    row = db.execute("select label from surveillance where symbol = ? and as_of = "
                     "(select max(as_of) from surveillance where as_of <= ?)", [symbol, day]).fetchone()
    return row[0] if row else None


def _previous(db, symbol: str, day: date) -> dict | None:
    """The last call on the stock: date, section, probability and summary. Never its score."""
    row = db.execute("select made_on, coalesce(section, action), probability, reasons from calls where symbol = ? "
                     "and made_on < ? order by made_on desc, id desc limit 1", [symbol, day]).fetchone()
    if not row:
        return None
    reasons = json.loads(row[3]) if isinstance(row[3], str) and row[3].startswith("{") else {}
    return {"date": str(row[0]), "section": row[1], "probability": row[2], "summary": reasons.get("summary")}


def _holding(p: Position, close: float, ctx: Context, day: date) -> dict:
    lots = [{"date": str(l.acquired_on), "qty": l.quantity, "cost": _r(l.cost), "long_term_on": str(l.turns_long_term_on)}
            for l in p.lots[:MAX_LOTS]]
    price = p.price or close
    tax = costs.tax_if_sold([{"acquired_on": l.acquired_on, "quantity": l.quantity, "cost": l.cost,
                              "turns_long_term_on": l.turns_long_term_on} for l in p.lots], price, day)
    out = {"qty": p.quantity, "avg_cost": _r(p.avg_cost), "value": round(p.value),
           "weight_pct": round(100 * p.value / ctx.portfolio_value, 1) if ctx.portfolio_value else None,
           "lots": lots, "tax_if_sold": {k: round(v) for k, v in tax.items()}}
    if len(p.lots) > MAX_LOTS:
        out["more_lots"] = len(p.lots) - MAX_LOTS
    return out


def build(db, symbol: str, day: date, *, ctx: Context | None = None) -> dict:
    ctx = ctx or Context(day, rates=load_rates(db))
    row = db.execute("select name, industry from stocks where symbol = ?", [symbol]).fetchone()
    name, industry = row if row else (symbol, None)
    d: dict = {"symbol": symbol, "name": name, "industry": industry}
    rows = _daily(db, symbol, day)
    if rows:
        d["price"] = _price_block(db, rows, day, symbol, industry, ctx)
        d["weekly"] = _weekly(rows, day)
    else:
        d["price"], d["weekly"] = {}, []
    if delivery := _delivery(db, symbol, day):
        d["delivery"] = delivery
    d.update(_fundamentals(db, symbol, day, industry, ctx))
    d.update(_quarters(db, symbol, day))
    d["results_on"] = _results_on(db, symbol, day)
    d["announcements"], d["headlines"] = _news(db, symbol, day)
    d["deals"] = _deals(db, symbol, day)
    d["flag"] = _flag(db, symbol, day)
    d["base_rate"] = base_rate(ctx.rates, ctx.candidates.get(symbol), ctx.regime, ctx.median_vol)
    d["previous"] = _previous(db, symbol, day)
    if h := blocks.history(db, symbol, day):
        d["history"] = h
    if g := blocks.gravity(db, symbol, day, d["price"], industry, blocks.size_ranks(db, day) if ctx.sizes is None else ctx.sizes):
        d["gravity"] = g
    if n := blocks.news(db, symbol, day, d["announcements"], d["headlines"], ctx.sector_index.get(industry)):
        d["news"] = n
    if (p := ctx.positions.get(symbol)) and rows:
        d["holding"] = _holding(p, rows[-1][3], ctx, day)
        if db.execute("select count(*) from long_term_marks where symbol = ?", [symbol]).fetchone()[0]:
            d["holding"]["long_term_mark"] = True      # "I hold this for years": judge it over years, not one quarter
    return d


# ---- the market -----------------------------------------------------------------------------------------

BREADTH_SQL = """
with t as (
    select symbol, date, close,
           avg(close) over w as ma, count(*) over w as n
    from prices where exchange = 'NSE' and date > $since and date <= $last
    window w as (partition by symbol order by date rows between 199 preceding and current row))
select date, avg((close > ma)::int) from t where n = 200 and date in $dates group by date
"""


def breadth(db, day: date, trading_days_back: int = 20) -> tuple[float | None, float | None]:
    """The share of NSE stocks above their own 200-day average, today and `trading_days_back` days ago."""
    dates = [r[0] for r in db.execute("select distinct date from prices where exchange = 'NSE' and date <= ? "
                                      "order by date desc limit ?", [day, trading_days_back + 1]).fetchall()]
    if len(dates) <= trading_days_back:
        return None, None
    wanted = [dates[0], dates[-1]]
    got = dict(db.execute(BREADTH_SQL, {"since": dates[-1] - timedelta(days=330), "last": dates[0],
                                        "dates": wanted}).fetchall())
    r = lambda d: round(got[d], 4) if d in got else None      # noqa: E731
    return r(wanted[0]), r(wanted[1])


def _percentile(values: list[float], x: float) -> float:
    return round(sum(v <= x for v in values) / len(values), 3)


def market(db, day: date, ctx: Context, industries: list[str], held: list[str]) -> dict:
    out: dict = {}
    nifty = db.execute("select date, close, pe from index_levels where name = 'Nifty 50' and date <= ? "
                       "and pe is not null order by date", [day]).fetchall()
    if nifty:
        pes = [r[2] for r in nifty]
        out["nifty"] = {"close": _r(nifty[-1][1]), "pe": _r(pes[-1]), "pe_percentile": _percentile(pes, pes[-1]),
                        "pe_days": len(pes)}
    now, ago = breadth(db, day)
    out["breadth"] = {"now": now, "20d_ago": ago}
    sectors, unmapped = {}, []
    for industry in sorted(set(i for i in industries if i)):
        index = ctx.sector_index.get(industry)
        ret = ctx.sector_returns.get(index) if index else None
        if ret is None:
            unmapped.append(industry)
        else:
            sectors[industry] = round(ret, 4)
    out["sectors"], out["unmapped_industries"] = sectors, unmapped
    if readiness.has_table(db, "flows"):
        rows = db.execute("select category, sum(net_cr), count(distinct date) from (select * from flows where date <= ? "
                          "and date in (select distinct date from flows where date <= ? order by date desc limit 5)) "
                          "group by category", [day, day]).fetchall()
        got = {c: (n, days) for c, n, days in rows}
        if got:
            out["flows"] = {"fii_net_5d_cr": round(got.get("FII", (0, 0))[0]), "dii_net_5d_cr": round(got.get("DII", (0, 0))[0]),
                            "days": max(days for _, days in got.values())}
    vix = db.execute("select close from index_levels where name = 'India VIX' and date <= ? and date > ? order by date",
                     [day, day - timedelta(days=365)]).fetchall()
    if vix:
        series = [v for (v,) in vix]
        out["vix"] = {"close": _r(series[-1]), "percentile_1y": _percentile(series, series[-1])}
    if held and readiness.has_table(db, "results_calendar"):
        marks = ",".join("?" * len(held))
        out["results_soon"] = [{"symbol": s, "date": str(d)} for s, d in db.execute(
            f"select symbol, min(date) from results_calendar where symbol in ({marks}) and date >= ? and date <= ? "
            "group by symbol order by 2", [*held, day, day + timedelta(days=10)]).fetchall()]
    return out
