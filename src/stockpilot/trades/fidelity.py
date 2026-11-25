"""Fidelity (ServiceNow RSU) vest and sale emails. NEEDS A REAL SAMPLE: wording assumed. A vest lot is the
net shares deposited at the vest-date fair market value (that value is the INR perquisite and the cost basis)."""
import re
from datetime import datetime

from stockpilot.trades.lots import Trade

NOW_ISIN = "US81762P1021"
VEST = re.compile(r"Vest\s+date\s*:\s*(\d{1,2}/\d{1,2}/\d{4})", re.I)
NET = re.compile(r"Net\s+shares\s+deposited\s*:\s*([\d,]+(?:\.\d+)?)", re.I)
VESTED = re.compile(r"Shares\s+vested\s*:\s*([\d,]+(?:\.\d+)?)", re.I)
FMV = re.compile(r"Fair\s+market\s+value\s+per\s+share\s*:\s*\$?\s*([\d,]+(?:\.\d+)?)", re.I)
SALE = re.compile(r"sold\s+([\d,]+(?:\.\d+)?)\s+shares\s+of\s+([A-Z]{1,5})\s+on\s+(\d{1,2}/\d{1,2}/\d{4})\s+at\s+\$?\s*([\d,]+(?:\.\d+)?)", re.I)
REF = re.compile(r"(?:Reference|Confirmation)\s*#?:?\s*([\w-]+)", re.I)


def _n(text: str) -> float:
    return float(text.replace(",", ""))


def _day(text: str):
    return datetime.strptime(text, "%m/%d/%Y").date()


def parse_email(body: str) -> Trade | None:
    ref = REF.search(body)
    if (m := VEST.search(body)) and (fmv := FMV.search(body)):
        qty = NET.search(body) or VESTED.search(body)
        if qty:
            day = _day(m[1])
            return Trade("fidelity", ref[1] if ref else f"vest:{day}", "rsu", "NOW", NOW_ISIN, "vest", day,
                         _n(qty[1]), _n(fmv[1]), currency="USD", trade_key=f"fidelity:vest:{day}")
    if m := SALE.search(body):
        day = _day(m[3])
        return Trade("fidelity", ref[1] if ref else f"sale:{day}", "rsu", m[2].upper(), NOW_ISIN, "sell", day,
                     _n(m[1]), _n(m[4]), currency="USD", trade_key=f"fidelity:sale:{day}:{m[1]}")
    return None
