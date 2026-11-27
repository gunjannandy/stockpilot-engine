"""NSE corporate actions: turn the `subject` text into a split or a bonus, and tell a share credit that
came from one of them apart from a real buy."""
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

SPLIT = re.compile(r"from\s+(?:rs\.?|re\.?|inr)?\s*(\d+(?:\.\d+)?)\D+?to\s+(?:rs\.?|re\.?|inr)?\s*(\d+(?:\.\d+)?)", re.I)
RIGHTS = re.compile(r"rights?\D*?(\d+)\s*:\s*(\d+).*?premium\D*?(\d+(?:\.\d+)?)", re.I)
BONUS = re.compile(r"bonus\D*?(\d+)\s*:\s*(\d+)", re.I)


@dataclass(frozen=True)
class Action:
    symbol: str
    isin: str | None
    ex_date: date
    kind: str          # split | bonus | demerger | rights (NSE gives a demerger no ratio and a rights issue no take-up)
    numerator: float   # split: new shares per `denominator` old; bonus: free shares per `denominator` held
    denominator: float
    subject: str = ""
    source: str = "nse"   # nse | yfinance | owner
    new_isin: str | None = None        # demerger: the company the shares come from
    new_symbol: str | None = None
    cost_fraction: float | None = None  # demerger: the part of the old cost that moves to the new shares
    price: float | None = None          # rights: rupees paid per new share; `ex_date` is then the allotment date


def from_nse(row: dict) -> Action | None:
    """One row of /api/corporates-corporateActions. None for anything that is not a split, bonus, demerger or rights."""
    subject = row.get("subject", "")
    low = subject.lower()
    ex = _day(row.get("exDate"))
    if not ex:
        return None
    sym, isin = row.get("symbol", ""), row.get("isin")
    if "bonus" in low and (m := BONUS.search(subject)):
        return Action(sym, isin, ex, "bonus", float(m[1]), float(m[2]), subject)
    if ("split" in low or "sub-division" in low or "subdivision" in low) and (m := SPLIT.search(subject)):
        old_fv, new_fv = float(m[1]), float(m[2])
        if new_fv > 0 and old_fv != new_fv:
            return Action(sym, isin, ex, "split", old_fv / new_fv, 1, subject)
    if "demerger" in low:   # NSE gives no ratio: the price factor comes from the ex-date jump (derive_demerger_factors)
        return Action(sym, isin, ex, "demerger", 1, 1, subject)
    if "rights" in low and (m := RIGHTS.search(subject)):
        paid = float(m[3]) + (_number(row.get("faceVal")) or 0.0)   # NSE quotes the premium over face value
        return Action(sym, isin, ex, "rights", float(m[1]), float(m[2]), subject, price=paid)
    return None


def _number(text):
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _day(text):
    for fmt in ("%d-%b-%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text or "", fmt).date()
        except ValueError:
            pass
    return None


def save(db, actions) -> int:
    n = 0
    for a in actions:
        db.execute("delete from corporate_actions where symbol = ? and ex_date = ? and kind = ?",
                   [a.symbol, a.ex_date, a.kind])
        db.execute("insert into corporate_actions (symbol, isin, ex_date, kind, numerator, denominator, subject, "
                   "source) values (?,?,?,?,?,?,?,?)",
                   [a.symbol, a.isin, a.ex_date, a.kind, a.numerator, a.denominator, a.subject, a.source])
        db.execute("delete from action_terms where symbol = ? and ex_date = ? and kind = ?", [a.symbol, a.ex_date, a.kind])
        if any(v is not None for v in (a.new_isin, a.new_symbol, a.cost_fraction, a.price)):
            db.execute("insert into action_terms values (?,?,?,?,?,?,?)",
                       [a.symbol, a.ex_date, a.kind, a.new_isin, a.new_symbol, a.cost_fraction, a.price])
        n += 1
    return n


DEMERGER_JUMP = 1.15   # the close must fall by more than 15% (before / on ex-date) to count as the demerger's price effect


def derive_demerger_factors(db) -> int:
    """For every demerger without a price factor: close before the ex-date / close on it, kept only when above
    DEMERGER_JUMP and no split or bonus shares the day (that jump is theirs). History is divided by it
    (analytics.ADJUSTED_SQL). Returns how many factors were set; run again as prices arrive."""
    set_ = 0
    for symbol, ex in db.execute("select symbol, ex_date from corporate_actions where kind = 'demerger' and "
                                 "(symbol, ex_date) not in (select symbol, ex_date from demerger_factors)").fetchall():
        if db.execute("select 1 from corporate_actions where symbol = ? and ex_date = ? and kind in ('split', 'bonus')",
                      [symbol, ex]).fetchone():
            continue
        on = db.execute("select close from prices where symbol = ? and exchange = 'NSE' and date >= ? "
                        "order by date limit 1", [symbol, ex]).fetchone()
        before = db.execute("select close from prices where symbol = ? and exchange = 'NSE' and date < ? "
                            "order by date desc limit 1", [symbol, ex]).fetchone()
        if on and before and on[0] and before[0] and before[0] / on[0] > DEMERGER_JUMP:
            db.execute("insert into demerger_factors values (?, ?, ?)", [symbol, ex, before[0] / on[0]])
            set_ += 1
    return set_


def classify_credit(actions, isin, on: date, quantity: float, held_before: float, window_days: int = 7,
                    tolerance: float = 0.5) -> str:
    """A share credit with no matching order: 'split', 'bonus', 'demerger', 'rights', or 'buy' (not explained by any
    action). The credit must land within `window_days` after the action's date and match its ratio to the share.
    `held_before` is what the account held of the company the action is about (for a demerger, the parent)."""
    for a in actions:
        target = a.new_isin if a.kind == "demerger" else a.isin
        if target not in (isin, None) or not 0 <= (on - a.ex_date).days <= window_days:
            continue
        ratio = a.numerator / a.denominator
        expected = held_before * (ratio - 1 if a.kind == "split" else ratio)
        if abs(quantity - expected) <= (tolerance if a.kind in ("split",) else max(tolerance, 1.0)):
            return a.kind
    return "buy"


LOOK_BACK_DAYS, LOOK_AHEAD_DAYS = 7, 45
NSE_LOG = "nse_corporate_actions"


def window_path(first: date, last: date) -> str:
    """The NSE corporate-actions request for first..last (the API wants DD-MM-YYYY)."""
    return ("/api/corporates-corporateActions?index=equities"
            f"&from_date={first.strftime('%d-%m-%Y')}&to_date={last.strftime('%d-%m-%Y')}")


def ingest(db, day: date, fetch_json) -> int:
    """Daily: splits and bonuses announced around `day` (a week back, six weeks ahead, so an ex-date is known
    before it arrives). Anything new triggers a lots rebuild, which restates history around the action."""
    from stockpilot.trades import lots
    rows = fetch_json(window_path(day - timedelta(days=LOOK_BACK_DAYS), day + timedelta(days=LOOK_AHEAD_DAYS))) or []
    found = [a for a in (from_nse(r) for r in rows) if a]
    new = [a for a in found if not db.execute("select 1 from corporate_actions where symbol = ? and ex_date = ? and "
                                              "kind = ?", [a.symbol, a.ex_date, a.kind]).fetchone()]
    save(db, found)
    derive_demerger_factors(db)
    if new and db.execute("select count(*) from trades").fetchone()[0]:
        lots.rebuild(db)
    return len(found)


def _months(since: date, today: date):
    y, m = since.year, since.month
    while (y, m) <= (today.year, today.month):
        first = date(y, m, 1)
        last = (date(y + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)
        yield first, last
        y, m = y + (m == 12), m % 12 + 1


def backfill(db, fetch_json, since: date, today: date) -> int:
    """History, one calendar month per request. A finished month is recorded in `fetch_log` and never fetched
    again; a failure stops the run (NSE is blocking us) and the next run resumes at that month. The month still
    running is fetched every time, because new announcements can land in it."""
    found = 0
    new_any = False
    try:
        for first, last in _months(since, today):
            period = first.strftime("%Y-%m")
            if db.execute("select 1 from fetch_log where source = ? and period = ?", [NSE_LOG, period]).fetchone():
                continue
            rows = fetch_json(window_path(first, last)) or []
            actions = [a for a in (from_nse(r) for r in rows) if a]
            new_any |= any(not db.execute("select 1 from corporate_actions where symbol = ? and ex_date = ? and "
                                          "kind = ?", [a.symbol, a.ex_date, a.kind]).fetchone() for a in actions)
            found += save(db, actions)
            if last < today:
                db.execute("insert into fetch_log values (?, ?)", [NSE_LOG, period])
    finally:
        derive_demerger_factors(db)
        _restate_lots(db, new_any)
    return found


def _restate_lots(db, new_any: bool) -> None:
    from stockpilot.trades import lots
    if new_any and db.execute("select count(*) from trades").fetchone()[0]:
        lots.rebuild(db)


JUMP = 0.4
MATCH_TRADING_DAYS = 2


def fallback_yfinance(db, fetch_splits, floor_cr: float, since: date = date(2015, 1, 1)) -> int:
    """Splits NSE did not list. For each liquid stock (3-month average traded value at or above `floor_cr`)
    that still shows a jump over 40% with no action, ask `fetch_splits(symbol)` -> [(date, ratio)] and keep
    a split only if its date is within two trading days of that jump. Returns how many were stored."""
    from stockpilot.analysis import quality
    stored = 0
    jumps: dict[str, list[date]] = {}
    for symbol, day, _ in quality.big_moves(db, JUMP, since):
        jumps.setdefault(symbol, []).append(day)
    for symbol, days in sorted(jumps.items()):
        adv = db.execute("select avg(value) / 1e7 from (select value from prices where symbol = ? "
                         "order by date desc limit 63)", [symbol]).fetchone()[0] or 0
        if adv < floor_cr:
            continue
        for when, ratio in fetch_splits(symbol) or []:
            if ratio and ratio > 0 and any(quality.within_trading_days(db, symbol, when, d, MATCH_TRADING_DAYS)
                                           for d in days):
                stored += save(db, [Action(symbol, None, when, "split", float(ratio), 1.0,
                                           f"yfinance split {ratio:g}:1", "yfinance")])
    return stored


def yfinance_splits(symbol: str):
    """The real fetcher for `fallback_yfinance`: yfinance `Ticker(<symbol>.NS).splits`. Imported lazily."""
    import yfinance as yf
    try:
        series = yf.Ticker(f"{symbol}.NS").splits
    except Exception:
        return []
    if series is None:
        return []
    return [(ts.date(), float(v)) for ts, v in series.items() if v]
