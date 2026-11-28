"""Every code-made sentence of a call (why, what could go wrong, we would buy if, limited evidence) is one template with
its English and Kolkata Bengali form (C-171-1). `{x}` placeholders must be the same in both forms."""
import re

TEMPLATES: dict[str, dict[str, str]] = {
    "why_buy": {"en": "Our model gives it a {chance} in 100 chance of beating the Nifty over {months} months, above our buy line of {line}.",
                "bn": "আমাদের মডেল বলছে {months} মাসে নিফটিকে হারানোর সম্ভাবনা ১০০-তে {chance}, যা আমাদের কেনার রেখা {line}-এর উপরে।"},
    "why_watch": {"en": "Our model gives it a {chance} in 100 chance of beating the Nifty over {months} months, close to our buy line of {line}.",
                  "bn": "আমাদের মডেল বলছে {months} মাসে নিফটিকে হারানোর সম্ভাবনা ১০০-তে {chance}, কেনার রেখা {line}-এর কাছাকাছি।"},
    "why_hold": {"en": "Our model gives it a {chance} in 100 chance of beating the Nifty over {months} months, between our sell and buy lines.",
                 "bn": "আমাদের মডেল বলছে {months} মাসে নিফটিকে হারানোর সম্ভাবনা ১০০-তে {chance}, বিক্রি ও কেনার রেখার মাঝামাঝি।"},
    "why_weak": {"en": "Our model gives it only a {chance} in 100 chance of beating the Nifty over {months} months, near our sell line of {line}.",
                 "bn": "আমাদের মডেল বলছে {months} মাসে নিফটিকে হারানোর সম্ভাবনা ১০০-তে মাত্র {chance}, বিক্রির রেখা {line}-এর কাছাকাছি।"},
    "why_sell": {"en": "Our model gives it only a {chance} in 100 chance of beating the Nifty over {months} months, below our sell line of {line}.",
                 "bn": "আমাদের মডেল বলছে {months} মাসে নিফটিকে হারানোর সম্ভাবনা ১০০-তে মাত্র {chance}, বিক্রির রেখা {line}-এর নিচে।"},
    "why_none": {"en": "We do not have enough price history to give a view yet.",
                 "bn": "মতামত দেওয়ার মতো দামের ইতিহাস এখনও আমাদের কাছে নেই।"},
    "wrong_range": {"en": "It could still fall to about ₹{low}; our range for {months} months runs from ₹{low} to ₹{high}.",
                    "bn": "এটি তবুও প্রায় ₹{low}-এ নামতে পারে; {months} মাসের জন্য আমাদের সীমা ₹{low} থেকে ₹{high}।"},
    "wrong_odds": {"en": "Even a good chance is not sure: about {miss} in 100 times like this, it did not beat the Nifty.",
                   "bn": "ভালো সম্ভাবনাও নিশ্চিত নয়: এমন ১০০ বারের মধ্যে প্রায় {miss} বার এটি নিফটিকে হারাতে পারেনি।"},
    "buy_if": {"en": "We would buy if the chance reaches {line} in 100.",
               "bn": "সম্ভাবনা ১০০-তে {line} ছুঁলে আমরা কিনব।"},
    "sell_if": {"en": "Sell at once if it falls to ₹{low}.", "bn": "₹{low}-এ নামলে সঙ্গে সঙ্গে বিক্রি করুন।"},
    "could_rise": {"en": "It could rise to about ₹{high}.", "bn": "এটি প্রায় ₹{high}-এ উঠতে পারে।"},
    "limited": {"en": "Limited evidence: the past cases behind this are few or have moved.",
                "bn": "প্রমাণ সীমিত: এর পেছনের আগের ঘটনা কম বা বদলে গেছে।"},
}
FIELD = re.compile(r"\{(\w+)\}")


def fields(text: str) -> set[str]:
    return set(FIELD.findall(text))


def render(key: str, **values) -> dict:
    t = TEMPLATES[key]
    return {"key": key, "en": t["en"].format(**values), "bn": t["bn"].format(**values)}
