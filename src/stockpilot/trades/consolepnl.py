"""Zerodha Console tax P&L workbooks (taxpnl .xlsx, and the older "P&L Statement" files): realised gains per
financial year, as Zerodha itself reports them. They feed one check (stage 7): our gains from the lots against
Console's, for the last financial year. Console's numbers are before charges and before the 31 Jan 2018 step-up.

Layout (checked on the real files for FY 2022-23 to 2025-26):
- sheet "Equity and Non Equity" (older: "Equity") and "Mutual Funds": a title "... from YYYY-MM-DD to YYYY-MM-DD", a
  "Realized Profit Breakdown" block of "<category> profit: amount", then tables with a "Symbol" header under a section
  name (Intraday, Short Term Trades, Long Term Trades, Non Equity; for funds "Short Term Trades Equity" and so on).
- the FY 2022-23 "P&L Statement" files have one "Summary" block with "Realized P&L" and one table with an ISIN column
  and no split by term: category "total".
A file's rows are added up per category and held against its own breakdown; a mismatch is listed in `problems`."""
import re
from dataclasses import dataclass, field
from datetime import date

from stockpilot.trades import xlsx

TITLE = re.compile(r"(?:Taxpnl|P&L) Statement for (Equity|Mutual Funds)\s+from\s+(\d{4}-\d{2}-\d{2})\s+to\s+(\d{4}-\d{2}-\d{2})", re.I)
BREAKDOWN = {"intraday/speculative profit": "intraday", "short term profit": "short_term", "long term profit": "long_term",
             "non equity profit": "non_equity", "short term profit equity": "short_term_equity",
             "long term profit equity": "long_term_equity", "short term profit debt": "short_term_debt",
             "long term profit debt": "long_term_debt", "debt - purchases post 2023-04-01": "debt_post_2023"}
SECTIONS = {"intraday": "intraday", "short term trades": "short_term", "long term trades": "long_term",
            "non equity": "non_equity", "short term trades equity": "short_term_equity",
            "long term trades equity": "long_term_equity", "short term trades debt": "short_term_debt",
            "long term trades debt": "long_term_debt", "debt - purchases post 2023-04-01": "debt_post_2023"}
TOLERANCE = 1.0   # rupees: the rows add up to the breakdown to the paisa, give or take rounding


@dataclass
class Row:
    category: str
    symbol: str
    isin: str | None
    quantity: float
    buy_value: float
    sell_value: float
    realised: float


@dataclass
class Statement:
    segment: str            # equity | mf
    fy: str                 # 2025-26
    period_start: date
    period_end: date
    totals: dict            # category -> realised profit, from the file's own breakdown
    rows: list = field(default_factory=list)
    problems: list = field(default_factory=list)


def _num(text) -> float | None:
    try:
        return float(str(text).replace(",", ""))
    except ValueError:
        return None


def _fy(start: date) -> str:
    year = start.year if start.month >= 4 else start.year - 1
    return f"{year}-{str(year + 1)[-2:]}"


def _statement(rows: list[dict]) -> Statement | None:
    title = next((m for r in rows[:20] if (m := TITLE.search(r.get("B", ""))) ), None)
    if not title:
        return None
    start, end = date.fromisoformat(title[2]), date.fromisoformat(title[3])
    st = Statement("mf" if title[1].lower().startswith("mutual") else "equity", _fy(start), start, end, {})
    section, columns = None, None
    for r in rows:
        label = (r.get("B") or "").strip()
        if len(r) == 1 and label.lower() in SECTIONS:
            section, columns = SECTIONS[label.lower()], None
        elif label.lower() in BREAKDOWN and "C" in r and section is None:
            st.totals[BREAKDOWN[label.lower()]] = _num(r["C"]) or 0.0
        elif label.lower() == "realized p&l" and "C" in r and section is None:   # the older "Summary" block
            st.totals["total"] = _num(r["C"]) or 0.0
        elif label == "Symbol":
            columns = ("D", "E", "F", "G", "C") if r.get("C") == "ISIN" else ("C", "D", "E", "F", None)
            if r.get("C") == "ISIN" and section is None:
                section = "total"
        elif columns and label and _num(r.get(columns[3], "")) is not None and label != "Symbol":
            q, b, s, p, i = columns
            st.rows.append(Row(section or "total", label, r.get(i) if i else None, _num(r[q]) or 0.0, _num(r.get(b, "")) or 0.0,
                               _num(r.get(s, "")) or 0.0, _num(r[p])))
    for category, stated in st.totals.items():
        found = sum(x.realised for x in st.rows if x.category == category)
        if abs(found - stated) > TOLERANCE:
            st.problems.append(f"{category}: the rows add up to {found:,.2f} but the file's breakdown says {stated:,.2f}")
    return st


def parse(data: bytes) -> list[Statement]:
    """One Statement per Equity and per Mutual Funds sheet. Raises when the workbook has neither."""
    book, out = xlsx.Workbook(data), []
    for name in book.sheets:
        if name.lower() in ("equity", "equity and non equity", "mutual funds"):
            if st := _statement(book.rows(name)):
                out.append(st)
    if not out:
        raise ValueError("Console tax P&L: no Equity or Mutual Funds statement found in the workbook")
    if any(r.isin is None for st in out for r in st.rows):
        isins = _tradewise_isins(book)
        for st in out:
            for r in st.rows:
                r.isin = r.isin or isins.get(r.symbol)
    return out


def _tradewise_isins(book) -> dict[str, str]:
    """The newer files print no ISIN beside a stock, but their "Tradewise Exits ..." sheet lists symbol and ISIN for
    every exit: that is how a renamed symbol (TWL, now TITAGARH) is recognised as one share."""
    out: dict[str, str] = {}
    for name in book.sheets:
        if name.lower().startswith("tradewise exits"):
            for r in book.rows(name):
                if r.get("B") and r.get("C", "").startswith("IN") and len(r["C"]) == 12:
                    out[r["B"]] = r["C"]
    return out


def save(db, statements: list[Statement], ref: str, modified: str) -> int:
    """Store statements. For one year and segment the file with the later period end wins, then the later
    modified time; an older file never overwrites a newer one. Returns the statements stored."""
    stored = 0
    for st in statements:
        old = db.execute("select max(period_end), max(modified) from console_pnl_totals where fy = ? and segment = ?",
                         [st.fy, st.segment]).fetchone()
        if old[0] is not None and (st.period_end, modified) < (old[0], old[1] or ""):
            continue
        db.execute("delete from console_pnl_totals where fy = ? and segment = ?", [st.fy, st.segment])
        db.execute("delete from console_pnl where fy = ? and segment = ?", [st.fy, st.segment])
        for category, profit in st.totals.items():
            db.execute("insert into console_pnl_totals values (?,?,?,?,?,?,?)",
                       [st.fy, st.segment, category, profit, st.period_end, ref, modified])
        for r in st.rows:
            db.execute("insert into console_pnl values (?,?,?,?,?,?,?,?,?,?)",
                       [st.fy, st.segment, r.category, r.symbol, r.isin, r.quantity, r.buy_value, r.sell_value,
                        r.realised, ref])
        stored += 1
    return stored


def _money(x: float) -> str:
    return f"{'-' if x < 0 else ''}₹{abs(x):,.0f}"


def check(db, fy: int, realised: list[dict]) -> list[str]:
    """Stage 7 check: our realised gains (`tax.realise` rows, before charges) against Console's for financial year
    `fy` (the year it starts, 2025 for 2025-26), in plain words. Empty when they agree or no Console file covers
    the year. Only sales up to the day the Console file ends are counted. Never blocks anything."""
    label = f"{fy}-{str(fy + 1)[-2:]}"
    totals = {(seg, cat): p for seg, cat, p in db.execute(
        "select segment, category, profit from console_pnl_totals where fy = ?", [label]).fetchall()}
    ends = db.execute("select max(period_end) from console_pnl_totals where fy = ?", [label]).fetchone()[0]
    if not totals:
        return []
    mine = [r for r in realised if date(fy, 4, 1) <= r["sold_on"] <= ends]

    def ours(pred):
        return sum(r["proceeds"] - r["cost"] for r in mine if pred(r))

    def theirs(segment, *cats):
        return sum(p for (seg, cat), p in totals.items() if seg == segment and (not cats or cat in cats))

    stock = lambda r: r["kind"] != "mf"   # noqa: E731
    lines = [
        ("short-term gain on shares", ours(lambda r: stock(r) and r["bucket"] == "equity" and r["term"] == "short"),
         theirs("equity", "intraday", "short_term", "total") if ("equity", "total") not in totals else None),
        ("long-term gain on shares", ours(lambda r: stock(r) and r["bucket"] == "equity" and r["term"] == "long"),
         theirs("equity", "long_term") if ("equity", "total") not in totals else None),
        ("gain on shares in all", ours(stock), theirs("equity") if ("equity", "total") in totals else None),
        ("gain on mutual funds", ours(lambda r: r["kind"] == "mf"), theirs("mf") if any(s == "mf" for s, _ in totals) else None),
    ]
    notes = []
    for what, mine_x, console_x in lines:
        if console_x is None:
            continue
        gap = mine_x - console_x
        if abs(gap) > max(100.0, 0.01 * abs(console_x)):
            notes.append(f"Console's tax P&L for {label} shows {_money(console_x)} {what}; our lots give {_money(mine_x)}, "
                         f"{_money(abs(gap))} {'more' if gap > 0 else 'less'}. Look at the trades behind it before filing.")
    notes += _per_share(db, label, mine)
    return notes


def _per_share(db, label: str, mine: list[dict]) -> list[str]:
    """The same comparison share by share, matched on ISIN so that a renamed symbol is one share, not two gaps.
    Console's gain per ISIN (every category except non-equity) against ours; silent when our rows carry no ISIN."""
    ours: dict[str, list] = {}
    for r in mine:
        if r.get("isin") and r["kind"] != "mf" and r["bucket"] == "equity":
            slot = ours.setdefault(r["isin"], [r.get("symbol") or r["isin"], 0.0])
            slot[1] += r["proceeds"] - r["cost"]
    if not ours:
        return []
    theirs = {isin: (symbol, gain) for isin, symbol, gain in db.execute(
        "select isin, any_value(symbol), sum(realised) from console_pnl where fy = ? and segment = 'equity' "
        "and isin is not null and category <> 'non_equity' group by isin", [label]).fetchall()}
    gaps = []
    for isin in ours.keys() | theirs.keys():
        name = (ours.get(isin) or theirs[isin])[0]
        a, b = ours.get(isin, (name, 0.0))[1], theirs.get(isin, (name, 0.0))[1]
        if abs(a - b) > max(500.0, 0.05 * abs(b)):
            gaps.append((abs(a - b), name, b, a))
    if not gaps:
        return []
    gaps.sort(reverse=True)
    shown = "; ".join(f"{name}: Console {_money(b)}, our lots {_money(a)}" for _, name, b, a in gaps[:5])
    more = f" (and {len(gaps) - 5} more)" if len(gaps) > 5 else ""
    return [f"Share by share, Console's tax P&L for {label} and our lots differ on {len(gaps)} "
            f"share{'s' if len(gaps) > 1 else ''}: {shown}{more}."]
