"""Fidelity NetBenefits documents (ServiceNow RSUs; PDF, password = PAN). Checked on the owner's real files:
- year-end report ("YEAR-END INVESTMENT REPORT"): the "Grant Transaction Details" table has an "RSU Vesting" row
  (units vested, fair market value) and an "RSU Distribution" row (units, value, net share proceeds) per vest.
  Grant and stock split rows are not vests.
- monthly statement ("STOCK PLAN SERVICES REPORT"): "Securities Bought & Sold" lists each RSU delivery as "You Bought u"
  (net shares at the vest-day price) and each sale as "You Sold" with its cost basis and proceeds. The date has no year:
  it comes from the period line above it.
- transaction summary ("Custom transaction summary"): "Stock sales" rows with the trade date, the vest it came from, cost
  and proceeds.
- Form 1042-S: the gross US income of the tax year (a few dollars of dividends).
The holdings export ("CSV Export") wraps its cells over lines, so its numbers cannot be read apart: it is refused with a reason.
`reconcile` holds the vests and sales found here against the ones in `trades` (including vests inferred from payslips
and the quarterly pattern) and says the differences in plain words."""
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from stockpilot.trades import pdftext

NEAR_DAYS = 6          # a delivery lands a few days after the vest day; a sale settles two days after its trade date


@dataclass
class Event:
    kind: str                          # vest | sale | dividend
    event_date: date
    quantity: float | None = None      # vest: units vested (statement: shares delivered); sale: shares sold
    net_quantity: float | None = None  # vest: shares deposited after withholding
    price_usd: float | None = None     # vest: fair market value per share; sale: price per share
    amount_usd: float | None = None    # vest: value of the delivery; sale: proceeds; dividend: gross income
    grant_id: str | None = None
    acquired_on: date | None = None    # sale: the day the shares were acquired
    cost_usd: float | None = None      # sale: cost basis


@dataclass
class Doc:
    kind: str                          # year_end | statement | transaction_summary | form_1042s
    events: list = field(default_factory=list)


def _n(text: str) -> float:
    return float(text.replace(",", ""))


def _year_end(text: str) -> Doc:
    vest = re.compile(r"^(\d{2}/\d{2}/\d{4}) \d{2}/\d{2}/\d{4} (\S+) RSU Vesting\s+([\d,.]+) \$?([\d,.]+) [\d,.]+$", re.M)
    dist = re.compile(r"^(\d{2}/\d{2}/\d{4}) \d{2}/\d{2}/\d{4} (\S+) RSU Distribution\s+[\d,.]+ \$?[\d,.]+ ([\d,.]+)$", re.M)
    net = {(m[1], m[2]): _n(m[3]) for m in dist.finditer(text)}
    events = []
    for m in vest.finditer(text):
        qty = _n(m[3])
        events.append(Event("vest", datetime.strptime(m[1], "%m/%d/%Y").date(), qty, net.get((m[1], m[2]), qty), _n(m[4]),
                            round(qty * _n(m[4]), 2), grant_id=m[2]))
    return Doc("year_end", sorted(events, key=lambda e: e.event_date))


def _period_year(header: re.Match, month: int) -> int:
    start_year, end_year = int(header[2]), int(header[4])
    if start_year == end_year:
        return start_year
    return start_year if month >= datetime.strptime(header[1].split()[0], "%B").month else end_year


def _statement(text: str) -> Doc:
    header = re.compile(r"^(\w+ \d{1,2}, (\d{4})) - (\w+ \d{1,2}, (\d{4}))$", re.M)
    lines, events, period, pending, value = text.splitlines(), [], None, None, None
    for i, line in enumerate(lines):
        if (h := header.match(line)) and i and "STOCK PLAN SERVICES REPORT" in lines[i - 1]:
            period = h
        elif m := re.match(r"^f?(\d{2})/(\d{2}) SERVICENOW", line):
            pending, value = (int(m[1]), int(m[2])), None
        elif pending and (m := re.match(r"^\$([\d,.]+)$", line)):
            value = _n(m[1])
        elif pending and period and (m := re.search(r"You Bought\s+u?\s*([\d,.]+) \$?([\d,.]+)", line)):
            qty, price = _n(m[1]), _n(m[2])
            events.append(Event("vest", date(_period_year(period, pending[0]), *pending), qty, qty, price,
                                value if value is not None else round(qty * price, 2)))
            pending = None
        elif pending and period and "81762P102 You Sold" in line:
            for follow in lines[i + 1:i + 4]:
                if m := re.match(r"^-([\d,.]+) ([\d,.]+) ([\d,.]+) (-?[\d,.]+) ([\d,.]+)$", follow):
                    events.append(Event("sale", date(_period_year(period, pending[0]), *pending), _n(m[1]), None,
                                        _n(m[2]), _n(m[5]), cost_usd=_n(m[3])))
                    break
            pending = None
    return Doc("statement", events)


def _transaction_summary(text: str) -> Doc:
    day = r"([A-Z][a-z]{2}-\d{2}-\d{4})"
    row = re.compile(rf"^{day} {day} ([\d.]+) \$([\d,.]+) \$([\d,.]+) [+-]?\s*\$[\d,.]+ USD\b", re.M)
    parse = lambda s: datetime.strptime(s, "%b-%d-%Y").date()   # noqa: E731
    return Doc("transaction_summary", [Event("sale", parse(m[1]), _n(m[3]), None, round(_n(m[5]) / _n(m[3]), 4), _n(m[5]),
                                             acquired_on=parse(m[2]), cost_usd=_n(m[4])) for m in row.finditer(text)])


def _form_1042s(text: str) -> Doc:
    year = re.search(r"Form 1042-S \((\d{4})\)", text)
    gross = re.search(r"2 Gross income\s*\n([\d,.]+)", text)
    if not (year and gross):
        raise ValueError("Fidelity 1042-S: could not read the tax year and the gross income")
    return Doc("form_1042s", [Event("dividend", date(int(year[1]), 12, 31), amount_usd=_n(gross[1]))])


def parse_text(text: str) -> Doc:
    if "YEAR-END INVESTMENT REPORT" in text:
        return _year_end(text)
    if "STOCK PLAN SERVICES REPORT" in text:
        return _statement(text)
    if "Custom transaction summary" in text:
        return _transaction_summary(text)
    if "Form 1042-S" in text:
        return _form_1042s(text)
    if text.lstrip().startswith("CSV Export"):
        raise ValueError("Fidelity holdings export: its cells wrap over lines, so quantities and costs cannot be read apart")
    raise ValueError("this is not a Fidelity year-end report, statement, transaction summary or 1042-S")


def parse_pdf(data: bytes, pan: str) -> Doc:
    return parse_text(pdftext.text(data, pan))


def save(db, doc: Doc, ref: str) -> None:
    """A document's events replace the rows its Drive id stored before."""
    db.execute("delete from fidelity_events where ref = ?", [ref])
    for e in doc.events:
        db.execute("insert into fidelity_events values (?,?,?,?,?,?,?,?,?,?)",
                   [ref, e.kind, e.event_date, e.grant_id, e.quantity, e.net_quantity, e.price_usd, e.amount_usd,
                    e.acquired_on, e.cost_usd])


# --- stage 7: Fidelity against the vests and sales we hold ---------------------------------------------------------

@dataclass
class Reconciliation:
    vests_matched: int = 0
    sales_matched: int = 0
    notes: list = field(default_factory=list)


def _day(d: date) -> str:
    return f"{d.day} {d:%b %Y}"


def _near(day: date, others, taken: set):
    """The unused one of `others` ((date, ...) tuples with an index) closest to `day` within NEAR_DAYS."""
    best = None
    for index, other in enumerate(others):
        gap = abs((other[0] - day).days)
        if index not in taken and gap <= NEAR_DAYS and (best is None or gap < best[0]):
            best = (gap, index)
    return best[1] if best else None


def _fidelity_vests(db) -> list[tuple]:
    """(date, vested, deposited) per vest day. The year-end report has gross and net per grant; a monthly statement only
    the shares delivered, a few days later, so it counts only where no year-end row sits near it."""
    rows = db.execute("select event_date, sum(quantity), sum(net_quantity), grant_id is not null from fidelity_events "
                      "where kind = 'vest' group by event_date, grant_id is not null order by event_date").fetchall()
    full = [(d, q, n) for d, q, n, has_grant in rows if has_grant]
    extra = [(d, q, n) for d, q, n, has_grant in rows if not has_grant and all(abs((d - f[0]).days) > NEAR_DAYS for f in full)]
    return sorted(full + extra)


def _fidelity_sales(db) -> list[tuple]:
    """(date, quantity) per sale: the transaction summary has the trade date; a statement sale counts only where the
    summary has none near it (its date is the settlement day)."""
    rows = db.execute("select event_date, quantity, acquired_on is not null from fidelity_events where kind = 'sale' "
                      "order by event_date").fetchall()
    exact = [(d, q) for d, q, summary in rows if summary]
    extra = [(d, q) for d, q, summary in rows if not summary
             and not any(abs((d - e[0]).days) <= NEAR_DAYS and abs(q - e[1]) < 0.01 for e in exact)]
    return sorted(exact + extra)


def reconcile(db) -> Reconciliation:
    out = Reconciliation()
    ours = db.execute("select trade_date, quantity, status from trades where side = 'vest' "
                      "and (symbol = 'NOW' or isin = 'US81762P1021') order by trade_date").fetchall()
    theirs, taken = _fidelity_vests(db), set()
    for day, vested, net in theirs:
        i = _near(day, ours, taken)
        if i is None:
            out.notes.append(f"Fidelity shows a ServiceNow vest of {vested:g} shares on {_day(day)}; we have no record of it.")
            continue
        taken.add(i)
        if abs(ours[i][1] - net) < 0.01:
            out.vests_matched += 1
        else:
            withheld = f" ({vested:g} vested)" if abs(vested - net) > 0.01 else ""
            out.notes.append(f"Fidelity shows {net:g} ServiceNow shares deposited from the {_day(day)} vest{withheld}; "
                             f"our record of that vest says {ours[i][1]:g}.")
    if theirs:
        low, high = theirs[0][0], theirs[-1][0]
        for i, (day, qty, _status) in enumerate(ours):
            if i not in taken and (low - day).days <= NEAR_DAYS and (day - high).days <= NEAR_DAYS:
                out.notes.append(f"We expect a ServiceNow vest of {qty:g} shares on {_day(day)}, but the Fidelity documents "
                                 "show none around that date.")
    mine = db.execute("select sold_on, quantity from sales where symbol = 'NOW' or isin = 'US81762P1021' order by sold_on").fetchall()
    sold, used = _fidelity_sales(db), set()
    for day, qty in sold:
        i = next((k for k, (d, q) in enumerate(mine) if k not in used and abs((d - day).days) <= NEAR_DAYS and abs(q - qty) < 0.01), None)
        if i is None:
            out.notes.append(f"Fidelity shows a sale of {qty:g} ServiceNow shares on {_day(day)}; we have no record of it.")
        else:
            used.add(i)
            out.sales_matched += 1
    if sold:
        for i, (day, qty) in enumerate(mine):
            if i not in used and (sold[0][0] - day).days <= NEAR_DAYS and (day - sold[-1][0]).days <= NEAR_DAYS:
                out.notes.append(f"We have a sale of {qty:g} ServiceNow shares on {_day(day)}, but the Fidelity documents show none then.")
    return out
