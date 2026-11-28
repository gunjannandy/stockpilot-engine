"""Chance to verdict, and the similar-calls count. The model forecasts; this alone says Buy, Watch, Hold, Weak or Sell.
`Trim` and a holding's own Sell (a stop reached) need what the person holds, which the public Job never sees: the browser
adds them from `money`. Lines come from config `rules` (buy 57, sell 40 in v2)."""
BUY_AT = 0.57
WATCH_AT = 0.52     # within five points of the buy line
SELL_AT = 0.40
SELL_HARD = 0.30    # well under the sell line
SIMILAR_WINDOW = 0.05
SIMILAR_LAST = 24


def verdict(chance: float | None) -> str:
    if chance is None:
        return "No view yet"
    if chance >= BUY_AT:
        return "Buy"
    if chance >= WATCH_AT:
        return "Watch"
    if chance > SELL_AT:
        return "Hold"
    if chance > SELL_HARD:
        return "Weak"
    return "Sell"


def similar(past: list[dict], call_verdict: str, chance: float, horizon_days: int) -> tuple[int, int]:
    """Our last calls like this one: same verdict and horizon, chance within 5 points. `past` rows are scored calls
    {made_on, verdict, chance, horizon_days, beat}. Returns (how many, how many beat the Nifty), newest 24 at most."""
    near = [p for p in past if p["verdict"] == call_verdict and p["horizon_days"] == horizon_days
            and abs(p["chance"] - chance) <= SIMILAR_WINDOW]
    near.sort(key=lambda p: p["made_on"], reverse=True)
    near = near[:SIMILAR_LAST]
    return len(near), sum(1 for p in near if p["beat"])
