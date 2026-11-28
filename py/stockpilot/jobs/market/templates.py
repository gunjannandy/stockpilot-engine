"""Market health sentences: one template each, English and Kolkata Bengali (same rule as the calls)."""
import re

TEMPLATES: dict[str, dict[str, str]] = {
    "trend_up": {"en": "The Nifty is {pct}% above its 200-day average: the trend is up.", "bn": "নিফটি তার ২০০ দিনের গড়ের {pct}% উপরে: প্রবণতা ঊর্ধ্বমুখী।"},
    "trend_down": {"en": "The Nifty is {pct}% below its 200-day average: the trend is down.", "bn": "নিফটি তার ২০০ দিনের গড়ের {pct}% নিচে: প্রবণতা নিম্নমুখী।"},
    "breadth": {"en": "{pct}% of the {n} largest stocks are above their 200-day average.", "bn": "সবচেয়ে বড় {n}টি শেয়ারের {pct}% তাদের ২০০ দিনের গড়ের উপরে।"},
    "value_cheap": {"en": "Stocks are cheap: the middle stock costs {pe} times a year's profit.", "bn": "শেয়ার সস্তা: মাঝামাঝি শেয়ারের দাম এক বছরের লাভের {pe} গুণ।"},
    "value_fair": {"en": "Stocks are fairly priced: the middle stock costs {pe} times a year's profit.", "bn": "শেয়ারের দাম ন্যায্য: মাঝামাঝি শেয়ারের দাম এক বছরের লাভের {pe} গুণ।"},
    "value_dear": {"en": "Stocks are dear: the middle stock costs {pe} times a year's profit.", "bn": "শেয়ার দামি: মাঝামাঝি শেয়ারের দাম এক বছরের লাভের {pe} গুণ।"},
}
FIELD = re.compile(r"\{(\w+)\}")


def fields(text: str) -> set[str]:
    return set(FIELD.findall(text))


def render(key: str, **values) -> dict:
    t = TEMPLATES[key]
    return {"key": key, "en": t["en"].format(**values), "bn": t["bn"].format(**values)}
