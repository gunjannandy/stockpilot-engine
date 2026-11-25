"""Base rate for a stock the owners hold, worked out from the stock's own price history.

The screen drops illiquid and exchange-watch-list names, so a holding the screen skipped has no row there. It still gets a
base rate: the same 40-bucket table (`base_rate_buckets`), placed by the stock's own momentum, volatility and liquidity.
A liquidity or watch-list flag only adds a plain risk line to the call. It never changes the chance and never makes a Sell."""
import re
from datetime import date

from stockpilot.analysis import analytics, backtest
from stockpilot.analysis.screen import MIN_DAYS, _percentiles

MIN_CASES = 30
MOMENTUM_METRICS = ("ret_12m", "ret_6m", "dist_200dma")
LIMITED_NO_HISTORY = "Limited evidence: too little price history to say how stocks like this usually do."
LIMITED_FEW_CASES = "Limited evidence: very few similar past cases to go on."
WATCH = re.compile(r"\b(?:(LT|ST)\s*)?(ASM|GSM)\b\s*(?:stage\s*)?([IVX]+|\d+)?", re.IGNORECASE)
NOT_A_SELL = "That is a risk to weigh, not a reason to sell on its own."


def needs_own_history(symbol: str, candidates: dict) -> bool:
    """True when the screen has no row for the stock, so its base rate cannot come from there."""
    return symbol not in candidates


def watch_line(label: str | None) -> str | None:
    """A plain sentence for an ASM or GSM label such as "STASM I", "LTASM I" or "GSM Stage 2". The call text never says ASM or GSM
    (prompts/plain-words.md bans both): it says "watch list", short-term or long-term, graded for GSM, and the stage."""
    m = WATCH.search(label or "")
    if not m:
        return None
    term, scheme, stage = m.group(1), m.group(2).upper(), m.group(3)
    where = f" (stage {stage.upper() if stage.isalpha() else stage})" if stage else ""
    kind = "graded " if scheme == "GSM" else {"ST": "short-term ", "LT": "long-term "}.get((term or "").upper(), "")
    return (f"The exchange has this stock on its {kind}watch list{where} for sharp price swings: take extra care. "
            + NOT_A_SELL)


def illiquid_line(adv_cr: float | None, floor_cr: float) -> str | None:
    if (adv_cr or 0) >= floor_cr:
        return None
    return (f"Thinly traded (about ₹{adv_cr or 0:.2f} crore a day): it can be hard to sell at a fair price, so size any sale "
            "with care. " + NOT_A_SELL)


def _momentum_bucket(own: dict, candidates: dict) -> int:
    """The stock's place among the screen's stocks on the same three momentum figures the screen uses, as one of five buckets."""
    parts = []
    for metric in MOMENTUM_METRICS:
        pool = {s: (c.get("metrics") or {}).get(metric) for s, c in candidates.items()}
        pool = {s: v for s, v in pool.items() if v is not None}
        if own.get(metric) is None or not pool:
            continue
        parts.append(_percentiles({**pool, "\0held": own[metric]}, True)["\0held"])
    score = sum(parts) / len(parts) if parts else 0.5
    return min(4, int(score * 5))


def for_held(db, symbol: str, day: date, *, rates: dict, regime: str, candidates: dict, median_vol: float | None,
             floor_cr: float = 1.0, factors: dict | None = None, screen_rate: dict | None = None) -> dict:
    """{rate, n, limited, limited_line, risk_line}: the base rate of a held stock from its own history.
    `factors` is `analytics.price_factors(db, day)`, passed in when several holdings are looked up on one day. `screen_rate`
    is the {rate, n} the screen already gave a stock it scored: that one is kept, and only the lines are added."""
    if factors is None:
        factors = analytics.price_factors(db, day)
    own = factors.get(symbol)
    label = db.execute("select label from surveillance where symbol = ? and as_of = "
                       "(select max(as_of) from surveillance where as_of <= ?)", [symbol, day]).fetchone()
    lines = [x for x in (illiquid_line(own["adv_3m_cr"], floor_cr) if own else None, watch_line(label[0] if label else None)) if x]
    out = {"rate": 0.5, "n": 0, "limited": True, "limited_line": LIMITED_NO_HISTORY, "risk_line": " ".join(lines) or None}
    if screen_rate:
        return {**out, **screen_rate, "limited": screen_rate["n"] < MIN_CASES, "limited_line": LIMITED_FEW_CASES}
    if not own or (own.get("days") or 0) < MIN_DAYS:
        return out
    calm, size = backtest.cut_of(own.get("vol_1y"), median_vol, own.get("adv_3m_cr"))
    bucket = _momentum_bucket(own, candidates)
    hit = rates.get((bucket, regime, calm, size)) or rates.get(("momentum", bucket, regime))   # the older coarse table, as the dossier does
    if not hit:
        return out
    n = int(hit["n"])
    return {**out, "rate": round(hit["hit_rate"], 3), "n": n, "limited": n < MIN_CASES, "limited_line": LIMITED_FEW_CASES}
