"""Every reason a stock is on a list is one template with its English and Kolkata Bengali form (same rule as the calls)."""
import re

TEMPLATES: dict[str, dict[str, str]] = {
    "rank": {"en": "Ranked {rank} of {passed} stocks that passed our checks.", "bn": "আমাদের পরীক্ষায় পাস করা {passed}টি শেয়ারের মধ্যে {rank} নম্বরে।"},
    "quality_top": {"en": "Among the best in its industry for quality.", "bn": "মানে নিজের শিল্পের সেরাদের মধ্যে।"},
    "value_top": {"en": "Among the cheapest in its industry for its earnings.", "bn": "আয়ের তুলনায় নিজের শিল্পের সবচেয়ে সস্তাদের মধ্যে।"},
    "momentum_top": {"en": "Its price has been rising steadily.", "bn": "এর দাম ধীরে ধীরে বাড়ছে।"},
    "risk_top": {"en": "Its price swings less than most in its industry.", "bn": "নিজের শিল্পের বেশিরভাগের চেয়ে এর দাম কম ওঠানামা করে।"},
    "missed": {"en": "Just missed the Top 10: ranked {rank}.", "bn": "সেরা ১০-এর ঠিক বাইরে: {rank} নম্বরে।"},
    "has_view": {"en": "We have a view: {verdict}, a {chance} in 100 chance of beating the Nifty.", "bn": "আমাদের মতামত আছে: {verdict}, নিফটিকে হারানোর সম্ভাবনা ১০০-তে {chance}।"},
    "falling": {"en": "Its price has been falling for months, in the weakest tenth of its industry.", "bn": "কয়েক মাস ধরে এর দাম পড়ছে, নিজের শিল্পের সবচেয়ে দুর্বল দশমাংশে।"},
    "busy_up": {"en": "Up {move}% from yesterday's close.", "bn": "গতকালের বন্ধের দামের চেয়ে {move}% বেশি।"},
    "busy_down": {"en": "Down {move}% from yesterday's close.", "bn": "গতকালের বন্ধের দামের চেয়ে {move}% কম।"},
}
FIELD = re.compile(r"\{(\w+)\}")


def fields(text: str) -> set[str]:
    return set(FIELD.findall(text))


def render(key: str, **values) -> dict:
    t = TEMPLATES[key]
    return {"key": key, "en": t["en"].format(**values), "bn": t["bn"].format(**values)}
