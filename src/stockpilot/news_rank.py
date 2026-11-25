"""PRIVATE (ticket T18): spread tagged news to the owners' holdings and watchlist, rank it, tier it, cap Sonnet.

Runs only as the `vm_private` job `news_rank`. Nothing here may be imported by public code or the public copy."""
from datetime import datetime, timedelta

CLOSENESS = {"holding": 4.0, "watchlist": 3.0, "sector": 2.0}
SONNET_AT_ONCE = 2
SONNET_PER_DAY = 6
HIGH_IMPACT = 4
MEDIUM_IMPACT = 3
MARKS = {"high": "yellow_dot", "medium": "yellow_dot", "low": "newspaper"}


def spread(items: list, holdings: set, watchlist: set, sector_map: dict) -> list[dict]:
    """One row per (item, owned stock it reaches): directly touched, or a list stock in the item's sector."""
    rows = {}
    for it in items:
        for t in it["touches"]:
            sym = t["symbol"]
            if sym in holdings or sym in watchlist:
                rows[(it["id"], sym)] = "holding" if sym in holdings else "watchlist"
        if it.get("sector"):
            for sym in sorted(holdings | watchlist):
                if sector_map.get(sym) == it["sector"]:
                    rows.setdefault((it["id"], sym), "sector")
        for t in it["touches"]:                      # a touched stock in a listed stock's sector
            for sym in sorted(holdings | watchlist):
                if t["symbol"] not in holdings | watchlist and sector_map.get(sym) and sector_map.get(sym) == sector_map.get(t["symbol"]):
                    rows.setdefault((it["id"], sym), "sector")
    return [{"item_id": k[0], "symbol": k[1], "closeness": v} for k, v in rows.items()]


def score(impact: int, closeness: str, age_hours: float, sources: int) -> float:
    freshness = 1.0 / (1.0 + max(age_hours, 0) / 12.0)
    return round(impact * CLOSENESS.get(closeness, 1.0) * freshness * max(sources, 1), 4)


def tier(impact: int, closeness: str) -> str:
    if impact >= HIGH_IMPACT and closeness in ("holding", "watchlist"):
        return "high"
    return "medium" if impact >= MEDIUM_IMPACT else "low"


def mark(row: dict) -> str:
    return MARKS[row["tier"]]


def rank(items: list, holdings: set, watchlist: set, sector_map: dict, now: datetime) -> list[dict]:
    """One row per item that reaches an owned stock, best first. `symbols` lists the owned stocks it reaches."""
    by_item = {}
    for r in spread(items, holdings, watchlist, sector_map):
        by_item.setdefault(r["item_id"], []).append(r)
    out = []
    for it in items:
        reach = by_item.get(it["id"])
        if not reach:
            continue
        best = max((r["closeness"] for r in reach), key=lambda c: CLOSENESS[c])
        age = (now - datetime.fromisoformat(it["published_at"])).total_seconds() / 3600
        out.append({"item_id": it["id"], "closeness": best, "score": score(it["impact"], best, age, it.get("source_count", 1)),
                    "tier": tier(it["impact"], best), "ranked_at": now.isoformat(timespec="seconds"),
                    "symbols": [r["symbol"] for r in reach if r["closeness"] == best]})
    return sorted(out, key=lambda r: -r["score"])


class SonnetGovernor:
    """At most 2 Sonnet refreshes at once and 6 a day; the rest take the cheap route. A stock is not refreshed twice in a day."""

    def __init__(self, day):
        self.day, self.used_today, self.running, self._done = day, 0, set(), set()

    def start(self, symbol: str, now: datetime) -> str:
        if now.date() != self.day:
            self.day, self.used_today, self._done = now.date(), 0, set()
        if symbol in self._done or symbol in self.running:
            return "skip"
        if len(self.running) >= SONNET_AT_ONCE or self.used_today >= SONNET_PER_DAY:
            return "cheap"
        self.running.add(symbol)
        self._done.add(symbol)
        self.used_today += 1
        return "sonnet"

    def finish(self, symbol: str) -> None:
        self.running.discard(symbol)


def refresh_plan(ranked: list, gov: SonnetGovernor, now: datetime) -> list[dict]:
    """What to do for each ranked item and stock: Sonnet (within the caps), the cheap route, or nothing."""
    plan = []
    for r in ranked:
        for sym in r["symbols"]:
            if r["tier"] == "high":
                model = gov.start(sym, now)
            else:
                model = "cheap" if r["tier"] == "medium" else None
            plan.append({"item_id": r["item_id"], "symbol": sym, "model": model, "mark": mark(r)})
    return plan


def handler(load, save):
    """Job handler for `news_rank`: `load()` -> (items, holdings, watchlist, sector_map, now); `save(rows)` stores them."""
    def run(ctx):
        items, holdings, watchlist, sector_map, now = load()
        ctx.progress(f"Ranking {len(items)} news items")
        rows = rank(items, holdings, watchlist, sector_map, now)
        save(rows)
        return f"Ranked {len(rows)} items"
    return run
