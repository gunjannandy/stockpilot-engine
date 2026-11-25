"""Income tax return documents from the owner's Drive (PDF, password = PAN). Four kinds, checked on the real files:
- acknowledgement ("INDIAN INCOME TAX RETURN ACKNOWLEDGEMENT"): the year's totals on one page.
- return (the filled-up ITR-2, 90k characters): the page prints each field as "label, code, value" on separate
  lines, so a figure is found by its label and code together (A2e, A9, B3a, B12, C3, 15e ...). Capital gains by head
  come from Schedule CG; Schedule FA is counted by its filled rows.
- intimation (the 143(1) order, English half): processed totals; only the capital gains head, not its split.
- tax_statement (the annual tax statement, Form 26AS style): the TDS credited. It carries its own PAN; `for_owner`
  says whether that is the one we hold the account for.
Amounts are Indian-grouped rupees ("13,07,234", negative "-1,00,404"). A figure that cannot be found raises: a
guessed zero would look like a real answer. The stage 7 check (`check`) holds the return against Console and our lots."""
import re
from dataclasses import dataclass
from datetime import date, datetime

from stockpilot.analysis import tax
from stockpilot.trades import pdftext

AMOUNT = r"(-?[\d,]+(?:\.\d+)?)"
FIELDS = ["total_income", "tax_payable", "interest_fees", "taxes_paid", "refund", "balance_due", "capital_gains_head",
          "stcg_equity", "stcg_total", "ltcg_equity", "ltcg_total", "tds_credited"]


@dataclass
class Doc:
    kind: str                    # acknowledgement | return | intimation | tax_statement
    assessment_year: str         # 2026-27
    fy: str                      # 2025-26
    form: str | None = None
    filed_on: date | None = None
    for_owner: bool | None = None
    total_income: float | None = None
    tax_payable: float | None = None        # net tax liability, before interest
    interest_fees: float | None = None
    taxes_paid: float | None = None
    refund: float | None = None
    balance_due: float | None = None
    capital_gains_head: float | None = None     # income chargeable under the head, after set-off
    stcg_equity: float | None = None            # shares and equity funds, STT paid (s.111A)
    stcg_total: float | None = None
    ltcg_equity: float | None = None            # s.112A
    ltcg_total: float | None = None
    tds_credited: float | None = None
    fa_present: bool | None = None
    fa_entries: int | None = None


def _n(text: str) -> float:
    return float(text.replace(",", ""))


def _find(text: str, pattern: str, what: str, required: bool = True):
    m = re.search(pattern, text, re.I)
    if not m:
        if required:
            raise ValueError(f"income tax return: could not read {what}")
        return None
    return m


def _amount(text: str, label: str, code: str, what: str, required: bool = True) -> float | None:
    """The figure printed after `label` (which may wrap over lines) and the field `code`, each on its own line."""
    m = _find(text, rf"{label}[^\n]*\n(?:[^\n]*\n){{0,3}}?{re.escape(code)}\s*\n{AMOUNT}\s*(?:\n|$)", what, required)
    return _n(m[1]) if m else None


def _fy(assessment_year: str) -> str:
    start = int(assessment_year[:4]) - 1
    return f"{start}-{str(start + 1)[-2:]}"


def _kind(text: str) -> str:
    if "INDIAN INCOME TAX RETURN ACKNOWLEDGEMENT" in text:
        return "acknowledgement"
    if "Annual Tax Statement" in text:
        return "tax_statement"
    if "Intimation u/s 143(1)" in text:
        return "intimation"
    if "SCHEDULE CG" in text and "INDIAN INCOME TAX RETURN" in text:
        return "return"
    raise ValueError("this is not an income tax return, acknowledgement, intimation or annual tax statement")


def _settle(doc: Doc, due: float | None, refund: float | None) -> None:
    doc.balance_due, doc.refund = due or 0.0, refund or 0.0


def _acknowledgement(text: str) -> Doc:
    ay = _find(text, r"Assessment\s*\n\s*Year\s*\n(\d{4}-\d{2})", "the assessment year")[1]
    doc = Doc("acknowledgement", ay, _fy(ay), _find(text, r"Form Number\s*\n(ITR-\d)", "the form")[1])
    doc.filed_on = datetime.strptime(_find(text, r"Date of filing\s*:\s*\n?\s*(\d{2}-[A-Za-z]{3}-\d{4})", "the filing date")[1], "%d-%b-%Y").date()
    doc.total_income = _n(_find(text, r"Total Income\s*\n1A\s*\n" + AMOUNT, "total income")[1])
    doc.tax_payable = _n(_find(text, r"Net tax payable\s*\n4\s*\n" + AMOUNT, "net tax payable")[1])
    doc.interest_fees = _n(_find(text, r"Interest and Fee Payable\s*\n5\s*\n" + AMOUNT, "interest and fee")[1])
    doc.taxes_paid = _n(_find(text, r"Taxes Paid\s*\n7\s*\n" + AMOUNT, "taxes paid")[1])
    stated = _n(_find(text, r"Refundable \(6-7\)\s*\n8\s*\n(?:\([+-]\)\s*)?" + AMOUNT, "the balance")[1])
    _direction(doc, stated)
    return doc


def _direction(doc: Doc, stated: float) -> None:
    """The form prints the balance unsigned in some places: it is a refund when more was paid than owed."""
    owed = (doc.tax_payable or 0) + (doc.interest_fees or 0)
    if doc.taxes_paid is not None and doc.taxes_paid > owed:
        _settle(doc, 0.0, stated)
    else:
        _settle(doc, stated, 0.0)


def _return(text: str) -> Doc:
    ay = _find(text, r"Assessment Year\s*\n(\d{4}-\d{2})", "the assessment year")[1]
    doc = Doc("return", ay, _fy(ay), _find(text, r"FORM\s*\n(ITR-\d)", "the form")[1])
    doc.total_income = _amount(text, r"Total income \(9 - 11\)", "12", "total income")
    doc.tax_payable = _amount(text, r"Net tax liability \(10-11d\)", "12", "net tax liability")
    doc.interest_fees = _amount(text, r"Total Interest and Fee Payable", "13e", "interest and fee")
    doc.taxes_paid = _amount(text, r"Total Taxes Paid \(15a", "15e", "taxes paid")
    doc.tds_credited = _amount(text, r"TDS \(total of column 5 of 20B", "15b", "TDS", required=False)
    doc.balance_due = _amount(text, r"Amount payable \(Enter if 14", "16", "the amount payable")
    doc.refund = _amount(text, r"Refund \(If 15e is greater", "17", "the refund")
    doc.stcg_equity = _amount(text, r"Short-term capital gain on equity share", "A2e", "short-term gain on shares")
    doc.stcg_total = _amount(text, r"Total Short-term Capital Gain", "A9", "total short-term gain")
    doc.ltcg_equity = _amount(text, r"LTCG u/s 112A \(column 14", "B3a", "long-term gain on shares")
    doc.ltcg_total = _amount(text, r"Total long term capital gain chargeable", "B12", "total long-term gain")
    doc.capital_gains_head = _amount(text, r"Income chargeable under the head", "C3", "the capital gains head")
    block = re.search(r"SCHEDULE FA - .*?(?=SCHEDULE 5A|\Z)", text, re.S)
    doc.fa_present = block is not None
    # a filled row names its country as "<code>-<name>" ("2-United States Of America"); the empty form has none
    doc.fa_entries = len(re.findall(r"^\d{1,3}-[A-Za-z][^\n]*$", block[0], re.M)) if block else 0
    return doc


def _intimation(text: str) -> Doc:
    ay = _find(text, r"\nAY\s*:?\s*\n(\d{4}-\d{2})", "the assessment year")[1]
    form = _find(text, r"ITR Form Type\s*\n(ITR)-?(\d)", "the form")
    doc = Doc("intimation", ay, _fy(ay), f"ITR-{form[2]}")
    doc.filed_on = datetime.strptime(_find(text, r"Date of Filing\s*\n(\d{2}/\d{2}/\d{4})", "the filing date")[1], "%d/%m/%Y").date()
    pair = AMOUNT + r"\s*\n" + AMOUNT      # as filed, then as computed under 143(1): the computed one is kept
    doc.total_income = _n(_find(text, r"Total Income\s*\n" + pair, "total income")[2])
    doc.tax_payable = _n(_find(text, r"Tax Liability after relief\s*\n" + pair, "tax liability")[2])
    doc.interest_fees = _n(_find(text, r"Total Interest And Fee[^\n]*\n" + pair, "interest and fee")[2])
    doc.taxes_paid = _n(_find(text, r"Total Taxes Paid[^\n]*\n" + pair, "taxes paid")[2])
    doc.capital_gains_head = _n(_find(text, r"Capital gains\s+" + AMOUNT + r"\s+" + AMOUNT, "the capital gains head")[2])
    _direction(doc, _n(_find(text, r"Net Amount Payable / Refundable\s*\n" + pair, "the balance")[2]))
    return doc


def _tax_statement(text: str) -> Doc:
    m = _find(text, r"Financial Year (\d{4}-\d{2}) Assessment Year (\d{4}-\d{2})", "the year")
    doc = Doc("tax_statement", m[2], m[1])
    rows = re.findall(r"^\d+ .+? [A-Z]{4}\d{5}[A-Z] [\d.]+ ([\d.]+) [\d.]+$", text.split("PART-II")[0], re.M)
    doc.tds_credited = sum(float(x) for x in rows)
    return doc


def parse_text(text: str, pan: str | None = None) -> Doc:
    kind = _kind(text)
    doc = {"acknowledgement": _acknowledgement, "return": _return, "intimation": _intimation,
           "tax_statement": _tax_statement}[kind](text)
    doc.for_owner = None if pan is None else bool(pan) and pan in text
    return doc


def parse_pdf(data: bytes, pan: str) -> Doc:
    return parse_text(pdftext.text(data, pan), pan)


def save(db, doc: Doc, ref: str, modified: str) -> None:
    """One row per document (its Drive id); a changed file replaces its row."""
    db.execute("delete from itr_documents where ref = ?", [ref])
    cols = ["ref", "kind", "assessment_year", "fy", "form", "filed_on", "for_owner", "fa_present", "fa_entries", "modified"] + FIELDS
    values = [ref, doc.kind, doc.assessment_year, doc.fy, doc.form, doc.filed_on, doc.for_owner, doc.fa_present,
              doc.fa_entries, modified] + [getattr(doc, f) for f in FIELDS]
    db.execute(f"insert into itr_documents ({', '.join(cols)}) values ({', '.join('?' * len(cols))})", values)


def load(db, assessment_year: str) -> Doc | None:
    """The year's documents merged into one view: the first non-empty figure wins, in the order return,
    intimation, acknowledgement. Statements of someone else's PAN are left out."""
    order = {"return": 0, "intimation": 1, "acknowledgement": 2}
    rows = db.execute("select kind, form, filed_on, fa_present, fa_entries, " + ", ".join(FIELDS) +
                      " from itr_documents where assessment_year = ? and kind <> 'tax_statement' "
                      "and coalesce(for_owner, true)", [assessment_year]).fetchall()
    if not rows:
        return None
    rows.sort(key=lambda r: order[r[0]])
    names = ["kind", "form", "filed_on", "fa_present", "fa_entries"] + FIELDS
    out = Doc("merged", assessment_year, _fy(assessment_year))
    for row in rows:
        for name, value in zip(names, row):
            if name != "kind" and getattr(out, name) is None and value is not None:
                setattr(out, name, value)
    return out


# --- stage 7: the filed return against Console and our lots ------------------------------------------------

def _money(x: float) -> str:
    return f"{'-' if x < 0 else ''}₹{abs(x):,.0f}"


def _apart(a: float, b: float) -> bool:
    return abs(a - b) > max(100.0, 0.01 * abs(b))


def check(db, fy: int, realised: list[dict], foreign_lots: int = 0) -> list[str]:
    """Plain-words notes comparing the income tax return for financial year `fy` (2025 for 2025-26) with Console's
    tax P&L for the same year and with our lots (`tax.realise` rows, before charges). Empty when they agree or no
    return is on file. Short and long gains on shares and equity funds (the 111A and 112A lines) are compared; the
    return's intraday and non-equity lines have no place there. Never blocks anything."""
    label = f"{fy}-{str(fy + 1)[-2:]}"
    doc = load(db, f"{fy + 1}-{str(fy + 2)[-2:]}")
    if doc is None:
        return []
    totals = {(seg, cat): p for seg, cat, p in db.execute(
        "select segment, category, profit from console_pnl_totals where fy = ?", [label]).fetchall()}
    ours = [r for r in realised if date(fy, 4, 1) <= r["sold_on"] <= date(fy + 1, 3, 31) and r["bucket"] == "equity"]

    def mine(term):
        return sum(r["proceeds"] - r["cost"] for r in ours if r["term"] == term)

    def console(*pairs):
        return sum(totals.get(p, 0.0) for p in pairs) if any(p in totals for p in pairs) else None

    # Console's old single-total layout has no split by term: nothing to compare the lines with there
    split = ("equity", "total") not in totals
    notes = []
    for what, filed, term, theirs in [
            ("short-term gain on shares", doc.stcg_equity, "short", console(("equity", "short_term"), ("mf", "short_term_equity"))),
            ("long-term gain on shares", doc.ltcg_equity, "long", console(("equity", "long_term"), ("mf", "long_term_equity")))]:
        if filed is None:
            continue
        others = [("Console", theirs if split else None), ("our lots", mine(term))]
        apart = [(who, v) for who, v in others if v is not None and _apart(v, filed)]
        if apart:
            shown = "; ".join(f"{who} {'shows' if who == 'Console' else 'give'} {_money(v)}" for who, v in apart)
            notes.append(f"The income tax return for {label} shows a {what} of {_money(filed)}; {shown}. "
                         "Check the trades behind it before the next filing.")
    if doc.stcg_equity is None and doc.capital_gains_head is not None:
        net = console(("equity", "short_term"), ("mf", "short_term_equity"), ("equity", "long_term"), ("mf", "long_term_equity"))
        # the first Rs 1.25 lakh of long-term gain on shares is exempt, so a processed return can rightly show none
        if split and net is not None and net > tax.rules_for(fy).ltcg_exempt and doc.capital_gains_head == 0:
            notes.append(f"The income tax return for {label} shows no capital gains, but Console's tax P&L shows a net gain of "
                         f"{_money(net)} on shares and funds. Losses carried forward could explain it; ask the tax adviser.")
    if doc.fa_present and doc.fa_entries == 0 and foreign_lots:
        notes.append(f"The income tax return for {label} has Schedule FA (foreign assets) with no entries, but the account holds "
                     "foreign shares. Ask the tax adviser whether it should list them.")
    if doc.balance_due:
        notes.append(f"The income tax return for {label} shows {_money(doc.balance_due)} of tax still to pay.")
    return notes
