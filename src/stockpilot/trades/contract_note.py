"""Zerodha equity contract note (PDF, password = PAN). Checked on real notes of three layouts (2020, 2023, 2024+).
Every layout has a trade table: order no, time, trade no, time, "NAME-EQ/ISIN" (the 2020 layout breaks the line
after the slash), B/S, exchange, quantity, rates, "(net total)". The price is net total / quantity, which holds in
every layout (the 2026 rows carry a brokerage column before the rate, the older ones do not)."""
import re
from datetime import datetime

from stockpilot.trades import pdftext
from stockpilot.trades.lots import Trade

DATE = re.compile(r"Trade\s*Date\s*[:\-]?\s*(?:\d{4}-\d{2}-\d{2}\s+)?(\d{2}/\d{2}/\d{4})", re.I)
ROW = re.compile(
    r"\d{6,}\s+\d{2}:\d{2}:\d{2}\s+(\d{5,})\s+\d{2}:\d{2}:\d{2}\s+"   # order no, time, trade no, time
    r"((?:[^\n/]|\n){1,60}?)\s*/\s*(IN[A-Z0-9]{10})\s+([BS])\s+(?:NSE|BSE)?\s*(\d+(?:\.\d+)?)"   # name/ISIN, side, exchange, quantity
    r"((?:[ \t]+[\d.,]+)+)[ \t]+\(?(-?[\d,]+\.\d+)\)?[ \t]*$", re.M)


def parse_pdf(data: bytes, pan: str) -> list[Trade]:
    return parse_text(pdftext.text(data, pan))


def parse_text(text: str) -> list[Trade]:
    m = DATE.search(text)
    if not m:
        return []
    day = datetime.strptime(m[1], "%d/%m/%Y").date()
    out = []
    for row in ROW.finditer(text):
        trade_no, name, isin, side, qty, _, total = row.groups()
        qty = float(qty)
        price = round(abs(float(total.replace(",", ""))) / qty, 4)
        name = re.sub(r"\s+", " ", name).strip()
        name = re.sub(r"[-\s]+(EQ|BE|BZ|SM|ST|BL|IL|GB|GS|N\d)$", "", name.strip())
        out.append(Trade("contract_note", trade_no, "stock", name, isin, "buy" if side == "B" else "sell", day,
                         qty, price, trade_key=trade_no))
    return out
