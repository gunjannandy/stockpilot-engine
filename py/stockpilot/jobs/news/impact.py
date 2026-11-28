"""Judge each news item once, per affected stock: relation, direction, size and why, in English and Bengali.

A sector-only link is a grey "sector news" mark and never carries a direction. One impact row per (item, stock); the
table is append-only, so an item already judged is never judged again."""
from stockpilot.modeljson import json_in

from .weights import FILING, source_weight

RELATIONS = ("self", "rival", "supplier", "customer", "sector")
DIRECTIONS = ("good", "bad", "mixed")
SIZES = ("small", "medium", "large")
BATCH = 10
ARTICLE_CHARS = 4000
PROMPT = ("Judge each news item once per affected stock. Reply with a JSON list, one object per id: id, touches (list of "
          "symbol, exchange NSE|BSE, relation self|rival|supplier|customer|sector, direction good|bad|mixed, size "
          "small|medium|large, why_en, why_bn: one plain line each). A stock linked only through its sector gets relation "
          "sector and no direction.\n")


def high_impact(item: dict) -> bool:
    """Filings and items many sources report are worth reading in full."""
    return source_weight(item["source"]) == FILING or (item.get("source_count") or 1) >= 3


def _brief(item: dict, article) -> str:
    line = f"id:{item['id']}|{item['title']}|{item['source']}"
    if article and high_impact(item):
        text = article(item["link"])
        if text:
            line += f"\nARTICLE: {text[:ARTICLE_CHARS]}"
    return line


def _row(item: dict, t: dict, at: str) -> dict:
    sector = t.get("relation") == "sector"
    return {"id": f"{item['id']}:{str(t['symbol']).upper()}", "item_id": item["id"], "symbol": str(t["symbol"]).upper(),
            "exchange": t.get("exchange") if t.get("exchange") in ("NSE", "BSE") else "NSE",
            "relation": t["relation"] if t.get("relation") in RELATIONS else "sector",
            "direction": None if sector or t.get("direction") not in DIRECTIONS else t["direction"],
            "size": t["size"] if t.get("size") in SIZES else "small",
            "sector_only": sector or t.get("relation") not in RELATIONS,
            "why_en": t.get("why_en") or "", "why_bn": t.get("why_bn") or "",
            "weight": source_weight(item["source"]), "judged_at": at}


def judge(items: list[dict], model, at: str, article=None) -> tuple[list[dict], list[str]]:
    """`model.ask(prompt) -> text`. Returns (rows, answered item ids). A batch the model answers badly is skipped whole:
    its ids are not answered, so the next run judges it again."""
    rows, answered = [], []
    for i in range(0, len(items), BATCH):
        batch = items[i:i + BATCH]
        by = {it["id"]: it for it in batch}
        try:
            got = json_in(model.ask(PROMPT + "\n".join(_brief(it, article) for it in batch)))
        except Exception:  # noqa: BLE001 - a bad answer leaves the batch for the next run
            continue
        for g in got if isinstance(got, list) else []:
            it = by.get(g.get("id")) if isinstance(g, dict) else None
            if it:
                answered.append(it["id"])
                rows += [_row(it, t, at) for t in g.get("touches") or [] if isinstance(t, dict) and t.get("symbol")]
    return rows, answered


def unjudged(items: list[dict], judged_ids: set[str]) -> list[dict]:
    return [i for i in items if i["id"] not in judged_ids]
