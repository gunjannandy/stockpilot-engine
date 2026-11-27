"""RSU vest inference. Confirmed vests come from Fidelity emails; the rest are projected from the quarterly
pattern (or from payslip perquisite months) and stay status "expected" until a document confirms them.
Expected vests are stored but never become lots."""
import re
from calendar import monthrange
from datetime import date, datetime

from stockpilot.trades.lots import Trade

PERIOD = re.compile(r"(?:Pay\s+Period\s*:|Payslip\s+for\s+the\s+month\s+of)\s*([A-Za-z]+)\s+(\d{4})", re.I)
# Real payslips (ServiceNow India, checked on two, both with 0.00): "STOCK OPTION GAIN GLOBAL : n" under "Miscellaneous
# Information", and "GAIN ON OPTIONS - INDIA INCOME : n". The first is the vest income; the second only when the first is absent.
PERQ = re.compile(r"(?:RSU|ESOP|Stock)\s+Perquisite\s+([\d,]+(?:\.\d+)?)|STOCK\s+OPTION\s+GAIN\s+GLOBAL\s*:?\s*([\d,]+(?:\.\d+)?)", re.I)
PERQ_INDIA = re.compile(r"GAIN\s+ON\s+OPTIONS\s*-\s*INDIA\s+INCOME\s*:?\s*([\d,]+(?:\.\d+)?)", re.I)
F16_AY = re.compile(r"Assessment\s+Year\s*:?\s*(\d{4})\s*-\s*(\d{2,4})", re.I)
# Real Form 16 (four checked): the pdf text prints Part B's line 1(b), "value of perquisites under section 17(2)", as
# "(b) <number>" right after the 17(1)(a) salary line; the label itself floats elsewhere on the page.
F16_PERQ = re.compile(r"section\s+17\(1\)\(a\)[^\n]*\n\s*\(b\)\s+([\d,]+(?:\.\d+)?)", re.I)
F16_PERQ_OLD = re.compile(r"perquisites?\s+(?:under|u/s)\s+section\s+17\(2\)\s+([\d,]+(?:\.\d+)?)", re.I)


def _n(text: str) -> float:
    return float(text.replace(",", ""))


def parse_payslip(text: str) -> tuple[str, float] | None:
    """('YYYY-MM', RSU perquisite in INR; 0.0 when the slip has none)."""
    m = PERIOD.search(text)
    if not m:
        return None
    month = datetime.strptime(f"{m[1][:3].title()} {m[2]}", "%b %Y")
    if q := PERQ.search(text):
        return month.strftime("%Y-%m"), _n(q[1] or q[2])
    q = PERQ_INDIA.search(text)
    return month.strftime("%Y-%m"), _n(q[1]) if q else 0.0


def parse_form16(text: str) -> tuple[str, float] | None:
    """(financial year 'YYYY-YY', section 17(2) perquisites in INR)."""
    ay, p = F16_AY.search(text), F16_PERQ.search(text) or F16_PERQ_OLD.search(text)
    if not ay or not p:
        return None
    start = int(ay[1]) - 1
    return f"{start}-{str(start + 1)[-2:]}", _n(p[1])


def _add_months(day: date, months: int) -> date:
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, min(day.day, monthrange(year, month + 1)[1]))


def expected_vests(confirmed: list[Trade], through: date, actions=(), every_months: int = 3) -> list[Trade]:
    """Project vests after the latest confirmed one, one per quarter up to `through`, repeating its size,
    scaled by any split with an ex-date between the last vest and the projected one."""
    vests = sorted((t for t in confirmed if t.side == "vest" and t.status == "confirmed"), key=lambda t: t.trade_date)
    if not vests:
        return []
    last, qty, out, step = vests[-1], vests[-1].quantity, [], 1
    while (when := _add_months(last.trade_date, every_months * step)) <= through:
        for a in actions:
            if a.kind == "split" and a.isin in (last.isin, None) and _add_months(last.trade_date, every_months * (step - 1)) < a.ex_date <= when:
                qty *= a.numerator / a.denominator
        out.append(Trade("rsu_inference", f"expected:{when}", "rsu", last.symbol, last.isin, "vest", when, round(qty, 4),
                         None, currency=last.currency, status="expected", trade_key=f"expected:{last.isin}:{when}"))
        step += 1
    return out


def vests_from_payslips(slips, price_inr, symbol="NOW", isin="US81762P1021") -> list[Trade]:
    """Months whose payslip shows an RSU perquisite are vest months. With no Fidelity email yet, estimate shares
    as perquisite / (price_inr(month)); the vest date is unknown, so it is the 15th."""
    out = []
    for month, perq in sorted(slips):
        if perq <= 0:
            continue
        when = datetime.strptime(month, "%Y-%m").date().replace(day=15)
        out.append(Trade("rsu_inference", f"payslip:{month}", "rsu", symbol, isin, "vest", when,
                         round(perq / price_inr(month), 4), None, currency="USD", status="expected",
                         trade_key=f"expected:{isin}:payslip:{month}"))
    return out
