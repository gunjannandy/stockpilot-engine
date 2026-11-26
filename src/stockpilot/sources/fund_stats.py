"""Fund stats for the fund page: each fund's yearly return over 1, 3 and 5 years, and the middle fund of each category month by
month (1-year return), so the page can say how a fund did against its kind without loading every fund file. Public data only
(AMFI NAVs). Published as `funds/stats.json` beside `funds/index.json`."""
from datetime import date
from statistics import median

MIN_CATEGORY = 5          # fewer funds than this is not a category worth a middle line
KEEP_MONTHS = 240         # 20 years of monthly points is more than any chart needs


def month_ends(series: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """[(YYYY-MM, last NAV of that month)] oldest first. Zero or missing NAVs (wound-up funds) are skipped."""
    last: dict[str, float] = {}
    for day, v in sorted((str(d)[:10], v) for d, v in series):
        if v and v > 0:
            last[day[:7]] = v
    return sorted(last.items())


def _months_back(ym: str, n: int) -> str:
    y, m = int(ym[:4]), int(ym[5:7])
    k = y * 12 + (m - 1) - n
    return f"{k // 12:04d}-{k % 12 + 1:02d}"


def yearly(ends: list[tuple[str, float]], years: int) -> float | None:
    """Yearly return in percent over the last `years` years, None when the fund is younger."""
    if not ends:
        return None
    by = dict(ends)
    last_ym, last_v = ends[-1]
    first = by.get(_months_back(last_ym, 12 * years))
    if first is None:
        return None
    return round(((last_v / first) ** (1 / years) - 1) * 100, 2)


def _roll1y(ends) -> dict[str, float]:
    by = dict(ends)
    out = {}
    for ym, v in ends:
        p = by.get(_months_back(ym, 12))
        if p:
            out[ym] = (v / p - 1) * 100
    return out


def build(entries: list[dict], nav: dict, built_at: str) -> dict:
    """`entries`: funds/index.json entries. `nav`: {primary code: [(date, nav)]}."""
    funds, per_cat = {}, {}
    for e in entries:
        ends = month_ends(nav.get(e["primary_code"]) or [])
        if len(ends) < 2:
            continue
        funds[e["id"]] = {"r1": yearly(ends, 1), "r3": yearly(ends, 3), "r5": yearly(ends, 5)}
        if e.get("category"):
            per_cat.setdefault(e["category"], []).append((e["id"], _roll1y(ends)))
    cats = {}
    for cat, members in per_cat.items():
        if len(members) < MIN_CATEGORY:
            continue
        months = sorted({m for _, r in members for m in r})[-KEEP_MONTHS:]
        line = []
        for m in months:
            vals = [r[m] for _, r in members if m in r]
            line.append(round(median(vals), 2) if len(vals) >= MIN_CATEGORY else None)
        keep = [(m, v) for m, v in zip(months, line) if v is not None]
        med = {k: [funds[i][k] for i, _ in members if funds[i][k] is not None] for k in ("r1", "r3", "r5")}
        cats[cat] = {"name": cat, "n": len(members), "months": [m for m, _ in keep], "med1y": [v for _, v in keep],
                     **{k: (round(median(v), 2) if v else None) for k, v in med.items()}}
    ids = list(funds)   # columns of equal length (the contract has no maps): id, r1, r3, r5
    return {"built_at": built_at, "funds": {"id": ids, **{k: [funds[i][k] for i in ids] for k in ("r1", "r3", "r5")}},
            "categories": list(cats.values())}
