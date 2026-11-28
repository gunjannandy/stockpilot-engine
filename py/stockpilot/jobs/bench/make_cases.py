"""Builds `cases.json`: made-up past public briefs, each with what happened next. Deterministic (seeded), so the file
never changes unless this script does. Run: `python -m stockpilot.jobs.bench.make_cases > cases.json`.

The outcome is drawn from the same signs the code's view counts, plus noise, so a good method beats chance without any case
being a copy of a real stock. Names and symbols are invented."""
import json
import random

from stockpilot.jobs.analyse.brief import FACT_KEYS, build

N = 30
SECTORS = ["Metals", "Banks", "Software", "Autos", "Pharma", "Power"]


def case(i: int, rng: random.Random) -> dict:
    roe, debt = rng.uniform(4, 28), rng.uniform(0, 2.4)
    pe_sector = rng.uniform(10, 30)
    facts = {"symbol": f"BNC{i:02d}", "name": f"Bench Company {i:02d}", "sector": SECTORS[i % len(SECTORS)],
             "pe": round(pe_sector * rng.uniform(0.5, 1.9), 1), "pe_sector": round(pe_sector, 1),
             "pb": round(rng.uniform(0.6, 6), 1), "roe_pct": round(roe, 1), "debt_to_equity": round(debt, 2),
             "profit_growth_yoy_pct": round(rng.uniform(-20, 40), 1), "pledge_pct": round(rng.choice([0, 0, 0, 8, 30]), 1),
             "market_cap_cr": round(rng.uniform(800, 90000))}
    ret, close = rng.uniform(-20, 25), rng.uniform(80, 900)
    history = [{"date": f"d{k}", "close": close * (1 + (ret / 100) * max(0, k - 236) / 63)} for k in range(300)]
    news = []
    if rng.random() < 0.5:
        good = rng.random() < 0.5
        news = [{"id": f"b{i}", "title": "Order win" if good else "Probe opened", "direction": "good" if good else "bad",
                 "size": rng.choice(["small", "medium", "large"]), "why_en": "Moves the next two quarters"}]
    brief = build(facts["symbol"], "2026-02-27", facts=facts, history=history, news=news)
    lean = (brief["code"]["chance_pct"] - 50) / 100 + (0.08 if news and news[0]["direction"] == "good" else
                                                         -0.08 if news else 0)
    beat = rng.random() < 0.5 + lean
    return {"id": f"case-{i:02d}", "brief": brief, "outcome": {"beat": beat, "excess_pct": round(rng.uniform(1, 18) * (1 if beat else -1), 1)}}


def cases() -> list[dict]:
    rng = random.Random(293)
    return [case(i, rng) for i in range(N)]


if __name__ == "__main__":
    assert FACT_KEYS
    print(json.dumps(cases(), ensure_ascii=False, indent=1))
