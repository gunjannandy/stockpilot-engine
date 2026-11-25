"""Tag new public news in batches of about 30 (ticket T18). Public side: it sees headlines only, never an owner's list.

The first model tags; if it fails or answers badly the fallback gets the same batch. Each tag has the sector, direction,
impact 1 to 5, one plain line in English and Bengali, and the stocks touched (rivals and suppliers too)."""
import json

BATCH = 30
RELATIONS = ("self", "rival", "supplier", "customer", "sector")
DIRECTIONS = ("good", "bad", "mixed")
SIZES = ("small", "medium", "large")
PROMPT = ("Tag each news item. Reply with a JSON list, one object per id: id, sector, direction (good|bad|mixed|none), "
          "impact (1 to 5), line_en, line_bn (one plain line each), touches (list of symbol, exchange NSE|BSE, "
          "relation self|rival|supplier|customer|sector, direction, size small|medium|large, changes_call bool).\n")


def batches(items: list, size: int = BATCH) -> list[list]:
    return [items[i:i + size] for i in range(0, len(items), size)]


def _clean(tag: dict) -> dict:
    touches = [{"symbol": str(t["symbol"]).upper(), "exchange": t.get("exchange") if t.get("exchange") in ("NSE", "BSE") else "NSE",
                "relation": t.get("relation") if t.get("relation") in RELATIONS else "sector",
                "direction": t.get("direction") if t.get("direction") in DIRECTIONS else "mixed",
                "size": t.get("size") if t.get("size") in SIZES else "small", "changes_call": bool(t.get("changes_call"))}
               for t in tag.get("touches") or [] if t.get("symbol")]
    impact = tag.get("impact")
    impact = min(5, max(1, impact)) if isinstance(impact, int) and not isinstance(impact, bool) else 1
    return {"id": tag["id"], "sector": tag.get("sector") or None,
            "direction": tag.get("direction") if tag.get("direction") in DIRECTIONS + ("none",) else "none",
            "impact": impact, "line_en": tag.get("line_en"), "line_bn": tag.get("line_bn"), "touches": touches}


def _ask(model, batch: list) -> list[dict]:
    lines = "\n".join(f"id:{it['id']}|{it['title']}|{it['source']}" for it in batch)
    got = json.loads(model.ask(PROMPT + lines))
    wanted = {it["id"] for it in batch}
    tags = [_clean(t) for t in got if isinstance(t, dict) and t.get("id") in wanted]
    if {t["id"] for t in tags} != wanted:
        raise ValueError("model skipped some items")
    return tags


def tag_all(items: list, model, fallback=None) -> list[dict]:
    out = []
    for batch in batches(items):
        try:
            out += _ask(model, batch)
        except Exception:  # noqa: BLE001 - any failure hands the batch to the next model
            if fallback is None:
                raise
            out += _ask(fallback, batch)
    return out


def handler(save):
    """Job handler for `news_tag`: payload {batch: [items]}; `save(tags)` stores them."""
    def run(ctx):
        batch = ctx.payload["batch"]
        ctx.progress(f"Tagging {len(batch)} news items")
        tags = tag_all(batch, ctx.model, getattr(ctx, "fallback", None))
        save(tags)
        return f"Tagged {len(tags)} items"
    return run
