"""The Analyse brief: public facts only, as one JSON document the model reads.

It is built from what the Worker serves to Jobs (the stock's facts, its daily history, the news impact rows). Holdings,
lots, tax, accounts, budget and preferences are not inputs here, so they cannot leak; `check_public` also refuses any
brief that carries a private-looking key, as a second lock."""
import json
import re

HORIZON_DAYS = 91
# Words that mark a private field. A key containing one is refused wherever it sits in the brief.
FORBIDDEN = ("holding", "lot", "quantity", "qty", "avg_price", "average_price", "cost_basis", "tax", "capital_gain", "pnl",
             "account", "owner", "budget", "wealth", "portfolio", "sip", "preference", "feedback")
_WORD = re.compile(r"[a-z]+")


class PrivateField(ValueError):
    """The brief carries a field that belongs to a person's money."""


def _private(key: str) -> bool:
    parts = [w[:-1] if w.endswith("s") and len(w) > 3 else w for w in _WORD.findall(str(key).lower())]
    joined = "_".join(parts)
    return any(f in parts or (len(f) > 4 and f in joined) for f in FORBIDDEN)


def check_public(node, path: str = "brief") -> None:
    """Raises PrivateField for the first key anywhere in `node` that names a holding, a tax figure or a person."""
    if isinstance(node, dict):
        for k, v in node.items():
            if _private(k):
                raise PrivateField(f"{path}.{k} is a private field")
            check_public(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            check_public(v, f"{path}[{i}]")


FACT_KEYS = ("pe", "pe_sector", "pb", "dividend_yield_pct", "market_cap_cr", "sales_growth_yoy_pct", "profit_growth_yoy_pct",
             "roe_pct", "roce_pct", "debt_to_equity", "promoter_pct", "pledge_pct")


def price_block(history: list[dict]) -> dict | None:
    """Close, 3-month return and 52-week range from daily rows ({date, close}, oldest first)."""
    rows = [r for r in history if r.get("close")]
    if len(rows) < 70:
        return None
    last = rows[-1]["close"]
    year = [r["close"] for r in rows[-250:]]
    return {"close": round(last, 2), "ret_3m_pct": round(100 * (last / rows[-64]["close"] - 1), 1),
            "high_52w": round(max(year), 2), "low_52w": round(min(year), 2)}


def code_view(facts: dict, price: dict | None) -> dict:
    """The code's own call from public numbers: a plain count of good and bad signs. The model may move it only with evidence."""
    score = 0
    def has(k): return facts.get(k) is not None
    if has("roe_pct"):
        score += 1 if facts["roe_pct"] >= 15 else -1 if facts["roe_pct"] < 8 else 0
    if has("debt_to_equity"):
        score += 1 if facts["debt_to_equity"] < 0.5 else -1 if facts["debt_to_equity"] > 1.5 else 0
    if has("profit_growth_yoy_pct"):
        score += 1 if facts["profit_growth_yoy_pct"] > 10 else -1 if facts["profit_growth_yoy_pct"] < 0 else 0
    if has("pe") and has("pe_sector"):
        score += 1 if facts["pe"] < facts["pe_sector"] else -1 if facts["pe"] > 1.5 * facts["pe_sector"] else 0
    if has("pledge_pct") and facts["pledge_pct"] > 20:
        score -= 1
    if price:
        score += 1 if price["ret_3m_pct"] > 5 else -1 if price["ret_3m_pct"] < -10 else 0
    chance = max(30, min(70, 50 + 5 * score))
    return {"call": "buy" if chance >= 60 else "avoid" if chance <= 40 else "watch", "chance_pct": chance}


def build(symbol: str, day: str, *, facts: dict | None, history: list[dict], news: list[dict]) -> dict:
    """`facts`: the stock's `facts` row. `news`: its impact rows (id, title, direction, size, why_en)."""
    facts = facts or {}
    figures = {k: facts[k] for k in FACT_KEYS if facts.get(k) is not None}
    price = price_block(history)
    items = [{"id": f"news:{n['id']}", "title": n.get("title", ""), "direction": n.get("direction"), "size": n.get("size"),
              "why": n.get("why_en", "")} for n in news[:8]]
    evidence = [f"fact:{k}" for k in figures] + (["price"] if price else []) + [i["id"] for i in items]
    gaps = [k for k in FACT_KEYS if k not in figures] + ([] if price else ["price"])
    brief = {"as_of": day, "symbol": symbol, "name": facts.get("name", ""), "sector": facts.get("sector", ""),
             "horizon_days": HORIZON_DAYS, "code": code_view(figures, price), "facts": figures, "price": price,
             "news": items, "evidence": evidence, "gaps": gaps}
    check_public(brief)
    return brief


def render(brief: dict, prompt: str) -> str:
    check_public(brief)
    return prompt + "\n\nBRIEF:\n" + json.dumps(brief, ensure_ascii=False, separators=(",", ":"))
