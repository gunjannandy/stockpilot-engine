"""Source weights (decisions §7): a filing outweighs a wire, a wire outweighs a blog. News is ranked by these, then by
how many sources agree, then by age."""
from datetime import datetime

FILING, WIRE, BLOG = 3, 2, 1
FILINGS = {"NSE", "BSE", "SEBI", "RBI"}
WIRES = {"reuters", "pti", "ani", "bloomberg", "economic times", "mint", "business standard", "businessline",
         "moneycontrol", "ndtv profit", "the hindu", "hindustan times", "cnbc-tv18"}


def source_weight(source: str) -> int:
    s = (source or "").strip()
    if s.upper() in FILINGS:
        return FILING
    if s.lower() in WIRES or any(w in s.lower() for w in ("reuters", "wire", "press trust")):
        return WIRE
    return BLOG


def rank_items(items: list[dict], now: datetime) -> list[dict]:
    """Best first: source weight, then distinct sources, then newest. Each item gets `weight`."""
    out = [{**i, "weight": source_weight(i["source"])} for i in items]
    out.sort(key=lambda i: i["published_at"], reverse=True)
    out.sort(key=lambda i: (-i["weight"], -(i.get("source_count") or 1)))
    return out
