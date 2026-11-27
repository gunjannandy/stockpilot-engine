"""CDSL consolidated account statement (PDF, password = PAN). Checked on real statements: the "HOLDING STATEMENT AS ON
dd-mm-yyyy" table lists, per ISIN, the name (one to five lines) and then "Current Bal, Frozen, Pledge, Pledge Setup,
Free, Price, Value". It gives quantities only, never prices, so it is a check on the lots (and explains nothing
about cost): a lot quantity that differs from `closing` is a gap in the trades."""
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from stockpilot.trades import pdftext

AS_ON = re.compile(r"HOLDING STATEMENT AS ON\s+(\d{2}-\d{2}-\d{4})")
ISIN = re.compile(r"^(IN[A-Z0-9]{10})\b(.*)$")
NUMS = re.compile(r"(?:^|\s)([\d,]+\.\d{3})\s+(?:--|[\d,]+\.\d+)\s+(?:--|[\d,]+\.\d+)\s+(?:--|[\d,]+\.\d+)\s+"
                  r"(?:--|[\d,]+\.\d+)\s+[\d,]+\.\d+\s+[\d,]+\.\d+\s*$")


@dataclass
class Statement:
    as_of: date | None = None
    closing: dict[str, float] = field(default_factory=dict)   # ISIN -> quantity held (all pledge states)


def parse_pdf(data: bytes, pan: str) -> Statement:
    return parse_text(pdftext.text(data, pan))


def parse_text(text: str) -> Statement:
    out, isin, inside = Statement(), None, False
    for line in text.splitlines():
        line = line.strip()
        if m := AS_ON.search(line):
            out.as_of, inside, isin = datetime.strptime(m[1], "%d-%m-%Y").date(), True, None
            continue
        if not inside:
            continue
        rest = line
        if m := ISIN.match(line):
            isin, rest = m[1], m[2]
        if isin and (m := NUMS.search(rest)):
            out.closing[isin] = float(m[1].replace(",", ""))
            isin = None
    return out
