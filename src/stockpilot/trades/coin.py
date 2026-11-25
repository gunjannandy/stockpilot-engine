"""Coin (Zerodha mutual funds) "Allotment Report" mails. Checked on a real mail: a row "date  FUND NAME  folio  Rs.
amount  Rs. stamp duty  NAV  units" (the amount may wrap onto the next line). The mail carries no ISIN, so the caller
may pass `isin_of(fund name)`. Price is amount / units, which is the cost per unit the Console tradebook shows.
The trade key matches the Console MF tradebook row for the same purchase (date, ISIN, side, units), so a unit
bought is counted once whichever document arrives."""
import re
from datetime import date

from stockpilot.trades.lots import Trade

ROW = re.compile(r"(\d{4}-\d{2}-\d{2})\s+(.+?)\s+(\d{5,})\s+Rs\.\s*([\d,]+(?:\.\d+)?)\s+Rs\.\s*[\d,.]+\s+[\d,.]+\s+([\d,]+\.\d+)")


def parse_email(body: str, isin_of=lambda name: None) -> list[Trade]:
    out = []
    for m in ROW.finditer(body):
        day, name, folio = date.fromisoformat(m[1]), re.sub(r"\s+", " ", m[2]).strip(), m[3]
        amount, units = float(m[4].replace(",", "")), float(m[5].replace(",", ""))
        isin = isin_of(name)
        out.append(Trade("coin", f"{folio}:{day}", "mf", name, isin, "buy", day, units, round(amount / units, 4),
                         trade_key=f"mf:{day}:{isin or name}:buy:{units:g}"))
    return out


REDEMPTION_ROW = re.compile(r"B?'([^'\n]+)'\s+T\d+\s+([\d,]+(?:\.\d+)?)\s+([\d,]+(?:\.\d+)?)\s+Rs\.\s*([\d,]+(?:\.\d+)?)")


def parse_redemption(body: str, day: date, isin_of=lambda name: None) -> list[Trade]:
    """Coin "Redemption report" (checked on a real mail): a row "'FUND NAME' T2 units NAV Rs. amount". The row has no
    date, so `day` is the mail's date: the order's day, which is the day the units leave. A sale at amount / units."""
    out = []
    for m in REDEMPTION_ROW.finditer(body):
        name = re.sub(r"\s+", " ", m[1]).strip()
        units, amount = float(m[2].replace(",", "")), float(m[4].replace(",", ""))
        isin = isin_of(name)
        out.append(Trade("coin", f"{day}:{name}:sell", "mf", name, isin, "sell", day, units, round(amount / units, 4),
                         trade_key=f"mf:{day}:{isin or name}:sell:{units:g}"))
    if not out:
        raise ValueError("Coin redemption mail: no redemption rows found")
    return out
