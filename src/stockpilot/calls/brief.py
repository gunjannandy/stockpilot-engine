"""The brief: everything judgement sees for one run, as one self-contained JSON document: the gaps in tonight's data, the
market block, and one entry per stock (its dossier, its code-set levels and hurdle, and why it is here). The model never
sees the budget, the owners' preferences or the track record."""
HORIZON_DAYS = 91


def entry(dossier: dict, why_here: list[str], levels: dict | None, hurdle: float | None) -> dict:
    """One stock's entry: the dossier plus what code decided about it."""
    e = dict(dossier)
    e["why_here"] = why_here
    if levels:
        e["levels"] = {k: levels[k] for k in ("entry", "stop", "target")}
    if hurdle is not None:
        e["hurdle_pct"] = round(100 * hurdle, 2)
    return e


def build(day, regime: str, market: dict, gaps: list[str], stocks: list[dict], house_rules: list[str] | None = None,
          review: str = "daily") -> dict:
    """`house_rules`: the owner-approved extra lines (the base file is in the prompt). `review`: "saturday" when every
    holding is in the call."""
    return {"as_of": str(day), "horizon_days": HORIZON_DAYS, "regime": regime, "review": review, "gaps": gaps,
            "house_rules": list(house_rules or []), "market": market, "stocks": stocks}


def for_skeptic(full: dict, answers: dict, borderline: list[str]) -> dict:
    """Only the borderline stocks, each with the analyst's answer beside its facts."""
    return {**full, "stocks": [{**s, "analyst": answers[s["symbol"]]} for s in full["stocks"] if s["symbol"] in borderline]}
