"""Check 3's machinery: price series with a close-to-close move over 40% that no corporate action explains.

A flagged series is excluded from the screen and from the calls, hidden on the site and listed in the gaps ledger, so a
missing split or a bad tick never becomes a number the father sees. `sync` keeps the `price_flags` table equal to the
jumps that still sit inside the window the screens and charts read."""
import json
from dataclasses import dataclass
from pathlib import Path
from datetime import date, timedelta

from stockpilot.analysis import analytics, quality

REASONS_FILE = Path(__file__).resolve().parents[3] / "config" / "price_flag_reasons.json"   # {"SYMBOL:YYYY-MM-DD": "why"}, written by hand after a look at the NSE feed
THRESHOLD = 0.4
WINDOW_DAYS = 400          # the daily part of a stock's chart, and more than the year the screens read
MIN_CLOSE = 5.0            # a close under ₹5 moves 40% on a few paise; that is a tick, not a data error
SPLIT_RATIOS = (2, 3, 4, 5, 8, 10, 20, 25, 50, 100)
PERSIST_DAYS = 15          # how long after the jump the price is looked at to tell a lasting shift from a bad tick


@dataclass(frozen=True)
class Flag:
    symbol: str
    jump_date: date
    move: float
    kind: str                  # split_like | reverse_split_like | level_shift | bad_tick
    close_before: float
    close_after: float


def classify(move: float, before: float, after: float, later: float | None, earlier: float | None = None) -> str:
    """Why a jump probably happened. `later` is the close about three weeks on (None when the series ends); `earlier` is
    the close about a week before the jump (a snap back to it means the day before was the bad tick)."""
    if earlier is not None and abs(after / earlier - 1) < 0.15 and abs(before / earlier - 1) > THRESHOLD:
        return "bad_tick"
    if later is not None and before and abs(later / before - 1) < 0.15 and abs(after / before - 1) > THRESHOLD:
        return "bad_tick"                      # it came back: one wrong close
    ratio = before / after if after else 0
    if move < 0 and any(abs(ratio / r - 1) < 0.06 for r in SPLIT_RATIOS):
        return "split_like"                    # price fell by a round ratio and stayed down: a split nobody listed
    ratio_up = after / before if before else 0
    if move > 0 and any(abs(ratio_up / r - 1) < 0.06 for r in SPLIT_RATIOS[:4]):
        return "reverse_split_like"
    return "level_shift"                       # demerger, rights issue, scheme of arrangement or a real crash


def scan(db, as_of: date, window_days: int = WINDOW_DAYS) -> list[Flag]:
    """Unexplained jumps over 40% in the last `window_days` (adjusted closes, so a listed split or bonus already counts as explained)."""
    since = as_of - timedelta(days=window_days)
    raw = quality.big_moves(db, THRESHOLD, since)
    out = []
    for symbol, day, move in raw:
        if day > as_of:
            continue
        rows = db.execute("select date, close from prices where symbol = ? and exchange = 'NSE' and date between ? and ? order by date",
                          [symbol, day - timedelta(days=10), day + timedelta(days=60)]).fetchall()
        if not rows:       # a BSE-only series
            rows = db.execute("select date, close from prices where symbol = ? and date between ? and ? order by date",
                              [symbol, day - timedelta(days=10), day + timedelta(days=60)]).fetchall()
        before = [c for d, c in rows if d < day]
        now = [c for d, c in rows if d == day]
        after = [c for d, c in rows if d > day]
        if not before or not now or min(before[-1], now[0]) < MIN_CLOSE:
            continue
        # the stored closes are raw; the move is in adjusted terms, so use it with the raw "before" level
        later = after[min(PERSIST_DAYS - 1, len(after) - 1)] if after else None
        earlier = before[-6] if len(before) >= 6 else None
        out.append(Flag(symbol, day, round(move, 4), classify(move, before[-1], now[0], later, earlier), before[-1], now[0]))
    return out


def sync(db, as_of: date) -> list[Flag]:
    """Make `price_flags` equal to the jumps found now; changes to the flags drop the stored screen so it is rebuilt without them."""
    found = scan(db, as_of)
    old = {(s, d) for s, d in db.execute("select symbol, jump_date from price_flags").fetchall()}
    now = {(f.symbol, f.jump_date) for f in found}
    db.execute("delete from price_flags")
    for f in found:
        db.execute("insert into price_flags values (?, ?, ?, ?, ?, ?, ?)",
                   [f.symbol, f.jump_date, f.move, f.kind, f.close_before, f.close_after, as_of])
    if old != now:
        db.execute("delete from screens")
    return found


def stored(db) -> set[tuple]:
    """(symbol, jump_date) of every stored flag; empty on a store that has not been migrated yet (a read-only look at an older file)."""
    try:
        return {(s, d) for s, d in db.execute("select symbol, jump_date from price_flags").fetchall()}
    except Exception:          # noqa: BLE001
        return set()


def flagged_symbols(db) -> set[str]:
    try:
        return {s for (s,) in db.execute("select distinct symbol from price_flags").fetchall()}
    except Exception:          # noqa: BLE001 - a store not yet migrated has no flags
        return set()


def flag_note(db, symbol: str) -> str:
    row = db.execute("select jump_date, move from price_flags where symbol = ? order by jump_date desc limit 1", [symbol]).fetchone()
    return f"price series unreliable: {row[1]:+.0%} in a day on {row[0]}" if row else "price series unreliable"


def recorded_reason(symbol: str, jump_date: date) -> str | None:
    """Why a flagged jump happened, when someone looked it up and wrote it in `config/price_flag_reasons.json`. The series stays
    hidden either way: a reason explains the flag, it does not make the price continuous."""
    try:
        return (json.loads(Path(REASONS_FILE).read_text()) or {}).get(f"{symbol}:{jump_date}")
    except (OSError, ValueError):
        return None
