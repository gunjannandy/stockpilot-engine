"""IPO allotment mails ("Allotment received - <company> IPO"). IPO shares arrive in the demat account with no contract
note, so this mail is their only trade: a buy at the issue price on the allotment date.
Checked on one real mail (tests/fixtures/trades/ipo_allotment_real.txt, anonymised: "allotted 12 shares of the X (SYM) IPO at a price of ₹1119/-", no allotment date, so the mail date is used); the older synthetic wording still parses. Anything the
parser cannot read raises, so a different layout shows up as a failed document instead of a missing holding.
The mail names the company, not the ISIN: `feed.store_all` matches the name to the NSE list."""
import re
from datetime import date, datetime

from stockpilot.trades.lots import Trade

SUBJECT = re.compile(r"allotment received\s*[-:–]?\s*(.+?)(?:\s+IPO)?\s*$", re.I)
# Real subjects (checked on four mails): "<Company> - Allotment received" or "<Company> IPO - Allotment received".
SUBJECT_REAL = re.compile(r"^\s*(.+?)(?:\s+IPO)?\s*[-–]\s*allotment received\s*$", re.I)
QTY = re.compile(r"(?:allotted\s+([\d,]+)\s+(?:equity\s+)?shares|(?:shares|quantity)\s+allotted\s*:?\s*([\d,]+))", re.I)
PRICE = re.compile(r"(?:(?:issue|offer|allotment)\s+price\s*:?|at a price\s+of)\s*(?:Rs\.?|₹|INR)?\s*([\d,]+(?:\.\d+)?)", re.I)
ALLOTTED_ON = re.compile(r"date of allotment\s*:?\s*(\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4})", re.I)


def parse_email(body: str, subject: str, mail_date: date) -> list[Trade]:
    name = SUBJECT_REAL.search(subject or "") or SUBJECT.search(subject or "")
    qty, price = QTY.search(body), PRICE.search(body)
    if not (name and qty and price):
        raise ValueError("IPO allotment mail: could not find the company, the shares and the issue price")
    when = mail_date
    if d := ALLOTTED_ON.search(body):
        for fmt in ("%d %b %Y", "%d %B %Y"):
            try:
                when = datetime.strptime(re.sub(r"\s+", " ", d[1]), fmt).date()
                break
            except ValueError:
                pass
    shares = float((qty[1] or qty[2]).replace(",", ""))
    company = name[1].strip()
    return [Trade("ipo", f"ipo:{company}:{when}", "stock", company, None, "buy", when, shares,
                  float(price[1].replace(",", "")), trade_key=f"ipo:{company}:{when}:{shares:g}")]
