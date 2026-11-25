"""Fidelity Stock Plan 'Current Shares' export: one row per lot, every cell wrapped over two or three lines, so the
text comes out scrambled. Words are placed by position: the header's first line gives each column's left edge, a row is
a run of lines with no big gap, a cell is the words under one column edge, top to bottom."""
import io
import re
from dataclasses import dataclass
from datetime import date, datetime

import pypdf

FIELDS = ["acquired", "quantity", "cost_basis", "cost_share", "value", "gain", "sale", "transfer", "grant", "source", "term"]
ROW_GAP = 20      # points: lines of one cell sit ~9 apart, rows ~36
TOL_SHARES, TOL_COST = 0.01, 1.0


@dataclass
class StatementLot:
    acquired_on: date
    quantity: float
    cost_basis_inr: float
    cost_per_share_inr: float
    value_inr: float
    gain_inr: float
    sale_available: date | None
    grant_date: date | None
    source: str
    term: str       # "short" | "long", Fidelity's own holding-period word


def _words(data: bytes) -> list[tuple[float, float, str]]:
    out = []

    def visit(text, cm, tm, font, size):
        if text.strip():
            out.append((tm[5], tm[4], text.strip()))
    pypdf.PdfReader(io.BytesIO(data)).pages[0].extract_text(visitor_text=visit)
    return out


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def _day(text: str) -> date | None:
    try:
        return datetime.strptime(text, "%b-%d-%Y").date()
    except ValueError:
        return None


def parse_pdf(data: bytes) -> list[StatementLot]:
    words = _words(data)
    head = next((y for y, x, t in words if t.startswith("Date ac")), None)
    if head is None:
        return []
    edges = sorted({round(x) for y, x, t in words if abs(y - head) < 1})
    if len(edges) != len(FIELDS):
        return []
    body = sorted((w for w in words if w[0] < head - 5), reverse=True)
    rows, last = [], None
    for y, x, t in body:
        if last is None or last - y > ROW_GAP:
            rows.append([])
        rows[-1].append((y, x, t))
        last = y
    lots = []
    for row in rows:
        cells = {f: "" for f in FIELDS}
        for y, x, t in sorted(row, key=lambda w: -w[0]):
            col = max((i for i, e in enumerate(edges) if x >= e - 2), default=None)
            if col is not None:
                cells[FIELDS[col]] += t
        if not (day := _day(cells["acquired"])):
            continue          # the footer note, not a lot
        try:
            lots.append(StatementLot(day, _num(cells["quantity"]), _num(cells["cost_basis"]), _num(cells["cost_share"]),
                                     _num(cells["value"]), _num(cells["gain"]), _day(cells["sale"]), _day(cells["grant"]),
                                     cells["source"], "long" if cells["term"].lower().startswith("long") else "short"))
        except ValueError:
            continue
    return lots


def agrees(lots: list[StatementLot], shares: float, cost_basis_inr: float) -> bool:
    """True when the lots add up to the holding Fidelity's Stock Plan page shows (shares and rupee cost)."""
    return bool(lots) and abs(sum(l.quantity for l in lots) - shares) <= TOL_SHARES \
        and abs(sum(l.cost_basis_inr for l in lots) - cost_basis_inr) <= TOL_COST


@dataclass
class Ingested:
    stored: int
    consistent: bool
    note: str


def ingest(db, data: bytes, as_of: date, symbol: str = "NOW", isin: str = "US81762P1021") -> Ingested:
    """Store the statement's lots when they hold together: every row's shares times cost per share is its cost basis, and
    the total is not more than what Fidelity's Stock Plan page shows today. Stored once per statement day (idempotent)."""
    lots = parse_pdf(data)
    if not lots:
        return Ingested(0, False, "No lots could be read from the statement.")
    if any(abs(l.quantity * l.cost_per_share_inr - l.cost_basis_inr) > 5 for l in lots):
        return Ingested(0, False, "A lot's shares times its cost per share is not its cost basis.")
    held = db.execute("select quantity from fidelity_holdings where symbol = ? order by as_of desc limit 1", [symbol]).fetchone()
    if held and sum(l.quantity for l in lots) > held[0] + TOL_SHARES:
        return Ingested(0, False, "The statement shows more shares than Fidelity's current page.")
    n = 0
    for l in lots:
        if not db.execute("select 1 from fidelity_lots where as_of = ? and symbol = ? and acquired_on = ? and cost_basis_inr = ?",
                          [as_of, symbol, l.acquired_on, l.cost_basis_inr]).fetchone():
            db.execute("insert into fidelity_lots values (?,?,?,?,?,?,?,?,?,?,?,?)",
                       [as_of, symbol, isin, l.acquired_on, l.quantity, l.cost_basis_inr, l.cost_per_share_inr, l.value_inr, l.gain_inr,
                        l.sale_available, l.grant_date, l.term])
            n += 1
    return Ingested(n, True, f"{len(lots)} lots, {sum(l.quantity for l in lots):g} shares as of {as_of}.")
