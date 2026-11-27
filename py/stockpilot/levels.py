"""Entry, stop and target, from the price structure alone. The model may flag a level with a reason; it never sets one.

Entry is the last close. The stop is half a daily move under the nearest support below entry, but never more than three
daily moves down (with no support below, two). The target is half of the stock's own typical three-month swing (daily move x the square root of 63), so a jumpy stock
aims higher than a calm one; a recent high at least one daily move away and inside that distance is used instead. It no longer
depends on the stop, and is less aggressive than the old "twice the risk" rule."""
from stockpilot import levels_calibration as calibration

MAX_STOP_MOVES = 3        # the stop is never further than this many daily moves below entry
NO_SUPPORT_MOVES = 2      # with no support below entry
BELOW_SUPPORT_MOVES = 0.5
HORIZON_DAYS = 63         # about three months of trading days: the positional style
SWING_SHARE = 0.5         # used when no measurement exists; `levels_calibration` measures the share that is reached about one time in two


def stop_for(p: dict) -> tuple[float, str] | None:
    """The stop and its plain reason, from a price block (close, atr, support)."""
    entry, atr = p.get("close"), p.get("atr")
    if not entry or not atr or atr <= 0:
        return None
    below = [s for s in p.get("support") or [] if s < entry]
    if below:
        floor = max(below)
        stop = max(floor - BELOW_SUPPORT_MOVES * atr, entry - MAX_STOP_MOVES * atr)
        stop_why = f"just under its recent low of ₹{floor:,.0f}" if stop < floor else f"{MAX_STOP_MOVES} daily moves down, the furthest allowed"
    else:
        stop = entry - NO_SUPPORT_MOVES * atr
        stop_why = f"{NO_SUPPORT_MOVES} daily moves down; no support found below"
    return stop, stop_why


def for_stock(dossier: dict) -> dict | None:
    p = dossier.get("price") or {}
    got = stop_for(p)
    if not got:
        return None
    stop, stop_why = got
    entry, atr = p["close"], p["atr"]
    share = calibration.share_for(p)
    swing = atr * HORIZON_DAYS ** 0.5            # how far a stock this jumpy typically travels in about three months
    aim = entry + share * swing
    near = [r for r in p.get("resistance") or [] if entry + atr <= r < aim]
    if near:
        target, target_why = min(near), f"its recent high of ₹{min(near):,.0f}"
    else:
        target_why = "about half a typical three-month move for this stock" if share == 0.5 else \
            f"about {round(100 * share)}% of a typical three-month move for this stock"
        target = aim
    entry, stop, target = round(entry, 2), round(stop, 2), round(target, 2)
    out = {"entry": entry, "stop": stop, "target": target,
           "why": f"If it falls to ₹{stop:,.0f} ({stop_why}), sell. Aim for ₹{target:,.0f} ({target_why})."}
    hit = calibration.hit_rate_for(p, (target - entry) / swing)
    if hit:
        out["target_hit_rate"], out["target_hit_n"] = hit
    return out
