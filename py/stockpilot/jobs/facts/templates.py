"""Every plain facts sentence is one template with its English and Kolkata Bengali form (C-171-2).
`{x}` placeholders are filled from the metric; both forms must use the same placeholders."""
import re

TEMPLATES: dict[str, dict[str, str]] = {
    "pe": {"en": "Priced at {pe} times a year's profit.", "bn": "এক বছরের লাভের {pe} গুণ দামে চলছে।"},
    "pe_cheaper": {"en": "Cheaper than its sector (middle {pe_sector} times).",
                   "bn": "সেক্টরের চেয়ে সস্তা (সেক্টরের মাঝামাঝি {pe_sector} গুণ)।"},
    "pe_dearer": {"en": "Dearer than its sector (middle {pe_sector} times).",
                  "bn": "সেক্টরের চেয়ে দামি (সেক্টরের মাঝামাঝি {pe_sector} গুণ)।"},
    "sales_up": {"en": "Sales grew {pct}% in the last year.", "bn": "গত এক বছরে বিক্রি {pct}% বেড়েছে।"},
    "sales_down": {"en": "Sales fell {pct}% in the last year.", "bn": "গত এক বছরে বিক্রি {pct}% কমেছে।"},
    "profit_up": {"en": "Profit grew {pct}% in the last year.", "bn": "গত এক বছরে লাভ {pct}% বেড়েছে।"},
    "profit_down": {"en": "Profit fell {pct}% in the last year.", "bn": "গত এক বছরে লাভ {pct}% কমেছে।"},
    "roe": {"en": "It earns {roe} rupees a year on every 100 of owners' money.",
            "bn": "মালিকদের প্রতি ১০০ টাকায় বছরে {roe} টাকা আয় করে।"},
    "debt_low": {"en": "Little or no debt.", "bn": "ঋণ প্রায় নেই।"},
    "debt": {"en": "Owes {debt} rupees for every 1 of owners' money.", "bn": "মালিকের প্রতি ১ টাকায় ঋণ {debt} টাকা।"},
    "promoter": {"en": "Promoters own {promoter}% of the company.", "bn": "প্রমোটারদের হাতে কোম্পানির {promoter}% আছে।"},
    "pledge_none": {"en": "Promoters have pledged none of their shares.", "bn": "প্রমোটাররা শেয়ার বন্ধক রাখেননি।"},
    "pledge": {"en": "Promoters have pledged {pledge}% of their shares.",
               "bn": "প্রমোটাররা নিজেদের শেয়ারের {pledge}% বন্ধক রেখেছেন।"},
    "biggest_fall": {"en": "Its biggest fall from a peak was {fall}%.", "bn": "চূড়া থেকে এর সবচেয়ে বড় পতন {fall}%।"},
    "swings": {"en": "Its price moves about {swing}% on a typical day.", "bn": "সাধারণ দিনে এর দাম প্রায় {swing}% ওঠানামা করে।"},
    "trading": {"en": "About {volume} shares change hands on a typical day.",
                "bn": "সাধারণ দিনে প্রায় {volume}টি শেয়ার হাতবদল হয়।"},
}


def fields(text: str) -> set[str]:
    return set(re.findall(r"{(\w+)}", text))


def render(key: str, **values) -> dict:
    t = TEMPLATES[key]
    return {"key": key, "en": t["en"].format(**values), "bn": t["bn"].format(**values)}
