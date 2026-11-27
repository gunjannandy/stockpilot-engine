"""The code check on each `_bn` field the model writes (`summary_bn`, `market_view_bn`). The prompt asks for plain Kolkata
Bengali with English words kept; this checks what code can check: not empty, not a copy of the English, mostly Bengali
script, no Hindi or Arabic script, and every number of the English sentence present unchanged. A field that fails is
blanked and the run says so; the page then shows the English."""
import re

BENGALI_DIGITS = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")
MIN_BENGALI_SHARE = 0.35        # of all letters; English names and words stay, so it is not 100%
DANDA = "\u0964\u0965"             # the Bengali full stop is in the Devanagari block; it is not Hindi
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers(text: str) -> list[str]:
    """Every number in the text as plain digits, commas removed: '₹১,২৫০' and '₹1,250' both give '1250'."""
    return [m.group().replace(",", "").rstrip(".") for m in NUMBER.finditer((text or "").translate(BENGALI_DIGITS))]


def _bengali_share(text: str) -> float:
    letters = [ch for ch in text if ch.isalpha()]
    return sum("ঀ" <= ch <= "৿" for ch in letters) / len(letters) if letters else 0.0


def problems(english: str, bengali: str) -> list[str]:
    text = (bengali or "").strip()
    if not text:
        return ["empty"]
    out = []
    if text == (english or "").strip():
        out.append("same as the English")
    if any(("ऀ" <= ch <= "ॿ" and ch not in DANDA) or "؀" <= ch <= "ۿ" for ch in text):
        out.append("contains Hindi or Arabic script")
    if _bengali_share(text) < MIN_BENGALI_SHARE:
        out.append("not mostly Bengali")
    missing = [n for n in numbers(english) if n not in numbers(text)]
    if missing:
        out.append("numbers missing or changed: " + ", ".join(missing))
    return out


def clean(english: str, bengali: str) -> tuple[str, list[str]]:
    """(the Bengali text, []) when it passes; ("", the problems) when it does not."""
    found = problems(english, bengali)
    return ("", found) if found else (bengali.strip(), [])
