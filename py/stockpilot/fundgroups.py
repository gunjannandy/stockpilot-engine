"""Plain-English fund groups for research. AMFI spells every category two ways ("Equity Scheme -" and "Equity Schemes -")
and lists thousands of sectoral, debt, arbitrage and index variants nobody is choosing between. A fund is researched only
when it falls in one of the groups below; everything else returns None."""
import re

# (group label, matches the AMFI category after its "Equity Scheme(s) -" / "Hybrid Scheme(s) -" prefix is removed)
_CATEGORY = [
    ("Large cap", r"^large cap"), ("Large & mid cap", r"^large & mid cap"), ("Mid cap", r"^mid cap"), ("Small cap", r"^small cap"),
    ("Flexi cap", r"^flexi cap"), ("Multi cap", r"^multi cap"), ("Focused", r"^focused"), ("Value and contra", r"^(value|contra)"),
    ("Dividend yield", r"^dividend yield"), ("Tax saving (ELSS)", r"^elss"), ("Tax saving (ELSS)", r"^elss"),
    ("Balanced advantage", r"^(balanced advantage|dynamic asset allocation)"), ("Aggressive hybrid", r"^aggressive hybrid"),
    ("Multi asset", r"^multi asset"),
]
_PREFIX = re.compile(r"^(equity|hybrid)\s+schemes?\s*-\s*", re.I)
_INDEX_MAIN = re.compile(r"nifty\s*50\b|nifty50|sensex|nifty\s*next\s*50", re.I)
_INDEX_MID = re.compile(r"midcap\s*150|smallcap\s*250|midcap\s*50|nifty\s*500", re.I)
ORDER = ["Large cap", "Flexi cap", "Mid cap", "Small cap", "Large & mid cap", "Multi cap", "Focused", "Value and contra",
         "Dividend yield", "Tax saving (ELSS)", "Balanced advantage", "Aggressive hybrid", "Multi asset",
         "Index (Nifty 50, Sensex)", "Index (mid and small cap)"]


def group_of(category: str | None, name: str | None = None) -> str | None:
    """The researched group of a scheme, or None when it is not one we compare (sectoral, debt, arbitrage, other indices...)."""
    cat = (category or "").strip()
    if not cat:
        return None
    if "index fund" in cat.lower():
        n = name or ""
        return "Index (Nifty 50, Sensex)" if _INDEX_MAIN.search(n) else "Index (mid and small cap)" if _INDEX_MID.search(n) else None
    if cat.lower() == "elss":
        return "Tax saving (ELSS)"
    body = _PREFIX.sub("", cat).lower()
    if body == cat.lower():
        return None
    for label, pat in _CATEGORY:
        if re.search(pat, body):
            return label
    return None
