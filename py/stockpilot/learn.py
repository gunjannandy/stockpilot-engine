"""R11: learn from what the owners set aside. A dismissal (the cross) and, at half weight, a snooze are read for the stock's
industry, size band and volatility band. A feature that shows up in at least 3 dismissals' worth within 60 days AND covers
at least 60% of that window's set-asides becomes a pattern ("Fewer banks"). Selection only: `forecast` marks a buy that
matches, `decide.sections` demotes it to the follow list. The model never sees a pattern (a test checks the model-side
modules do not import this one). A sell or trim is never touched; undoing a dismissal removes its weight; Forget switches a
pattern off for 90 days."""
import re
from datetime import date, datetime, timedelta
from statistics import median

WINDOW_DAYS = 60
MIN_WEIGHT = 3.0          # dismissals' worth: a dismissal is 1, a snooze half
SNOOZE_WEIGHT = 0.5
MIN_SHARE = 0.60
FORGET_DAYS = 90
LARGE_CR = 20.0           # same cut as the backtest: a day's traded value above this is "large"
SMALL_CR = 2.0
FEATURES = ("industry", "size", "vol")
PRICE_BANDS = ((100, "under 100"), (1000, "100 to 1,000"))


def features(result: dict) -> dict[str, dict]:
    """symbol -> {industry, size, vol, price, factors}, read from the screen result. `vol` is relative to the median
    1-year volatility of the screened stocks, the way the backtest cuts it."""
    cands = result.get("candidates") or []
    vols = [c["metrics"]["vol_1y"] for c in cands if c["metrics"].get("vol_1y") is not None]
    mid = median(vols) if vols else None
    out = {}
    for c in cands:
        m = c["metrics"]
        adv, vol, close = m.get("adv_3m_cr"), m.get("vol_1y"), m.get("close")
        out[c["symbol"]] = {
            "industry": c.get("industry"),
            "size": None if adv is None else "large" if adv > LARGE_CR else "small" if adv < SMALL_CR else "mid",
            "vol": None if vol is None or mid is None else "jumpy" if vol > mid else "calm",
            "price": None if close is None else next((t for hi, t in PRICE_BANDS if close < hi), "over 1,000"),
            "factors": dict(c.get("scores") or {})}
    return out


def _text(feature: str, value: str) -> str:
    return {"industry": f"Fewer {value.lower()}", "size": f"Fewer {value} stocks", "vol": f"No {value} stocks"}[feature]


def forgotten(db, day: date) -> set[str]:
    return {p for (p,) in db.execute("select pattern from learned_forgotten where until >= ?", [day]).fetchall()}


def _window(db, day: date) -> dict[str, float]:
    """symbol -> weight of its buy-side set-asides in the last 60 days, undone ones left out; a stock counts once, at its
    heaviest."""
    since = datetime.combine(day - timedelta(days=WINDOW_DAYS), datetime.min.time())
    weights: dict[str, float] = {}
    for symbol, how in db.execute("select symbol, how from not_now where undone_at is null and scope in ('buy', 'any') "
                                  "and set_at >= ?", [since]).fetchall():
        w = 1.0 if how == "dismiss" else SNOOZE_WEIGHT
        weights[symbol] = max(weights.get(symbol, 0.0), w)
    return weights


def patterns(db, day: date, result: dict, ignore_forgotten: bool = False) -> list[dict]:
    """The learned patterns in force on `day`, strongest first. Stocks the screen cannot describe are left out of the count."""
    feats = features(result)
    weights = {s: w for s, w in _window(db, day).items() if s in feats}
    total = sum(weights.values())
    if total <= 0:
        return []
    off = set() if ignore_forgotten else forgotten(db, day)
    tally: dict[tuple[str, str], dict] = {}
    for symbol, w in weights.items():
        for feature in FEATURES:
            value = feats[symbol].get(feature)
            if not value:
                continue
            t = tally.setdefault((feature, value), {"weight": 0.0, "dismissals": 0, "snoozes": 0})
            t["weight"] += w
            t["dismissals" if w == 1.0 else "snoozes"] += 1
    found = []
    for (feature, value), t in tally.items():
        key = f"{feature}:{value}"
        if t["weight"] >= MIN_WEIGHT and t["weight"] / total >= MIN_SHARE and key not in off:
            found.append({"pattern": key, "text": _text(feature, value), "feature": feature, "value": value,
                          "dismissals": t["dismissals"], "snoozes": t["snoozes"], "share": round(t["weight"] / total, 3),
                          "_w": t["weight"]})
    found.sort(key=lambda p: (-p["_w"], p["pattern"]))
    for p in found:
        del p["_w"]
    return found


def match(found: list[dict], feats: dict | None) -> str | None:
    """The text of the first learned pattern this stock fits, or None."""
    for p in found:
        if feats and feats.get(p["feature"]) == p["value"]:
            return p["text"]
    return None


def forget(db, pattern, day: date) -> str:
    """Switch a pattern off for 90 days (again: from the new day)."""
    if not isinstance(pattern, str) or not re.fullmatch(r"(industry|size|vol):\S.*", pattern.strip()):
        raise ValueError("Forget needs a pattern such as 'industry:Banks'.")
    pattern = pattern.strip()
    db.execute("insert or replace into learned_forgotten (pattern, until) values (?, ?)",
               [pattern, day + timedelta(days=FORGET_DAYS)])
    return pattern


def payload(db, day: date, result: dict) -> dict:
    """site/data/learned.json: each pattern with how many dismissals made it, and the Forget request to post."""
    rows = patterns(db, day, result)
    for p in rows:
        p["forget"] = {"kind": "learned_forget", "pattern": p["pattern"]}
    off = db.execute("select pattern, until from learned_forgotten where until >= ? order by pattern", [day]).fetchall()
    return {"as_of": str(day), "window_days": WINDOW_DAYS, "patterns": rows,
            "forgotten": [{"pattern": p, "until": str(u)} for p, u in off]}
