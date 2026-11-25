"""The trade feed: ask the Google bridge for new mail and Drive files, route each to its parser, and store
what came out. One bad document is recorded in `failed` and never stops the rest.

Mail is classified from the list entry alone (subject and attachment types), so mail nobody parses is never
downloaded: the bridge has a daily Gmail quota. Drive files are classified by content. docs/status/documents.md
lists every type and what it gives."""
import re
from dataclasses import dataclass, field, replace
from datetime import date, datetime

from stockpilot.sources import google
from stockpilot.trades import (cas, coin, consolepnl, contract_note, fidelity, fidelity_docs, ipo, itr, lots, pdftext, rsu,
                               smallcase, tradebook)

ALL_HISTORY = "2015-01-01T00:00:00Z"   # the bridge's own default is 400 days; the first sync needs everything
PARSERS = "7"  # bump when a parser changes what it reads: every document is then parsed again (from the cache)


@dataclass
class FeedResult:
    trades: list = field(default_factory=list)
    statements: list = field(default_factory=list)   # CDSL CAS statements: quantities per ISIN for reconciliation
    skipped: list = field(default_factory=list)      # ids of documents of a kind nobody has classified yet
    ignored: list = field(default_factory=list)      # (id, reason) known and deliberately not used
    failed: list = field(default_factory=list)       # (id, reason)
    deferred: list = field(default_factory=list)     # ids the bridge's daily limit kept us from reading: next sync
    handled: list = field(default_factory=list)      # dicts for the documents table: parsed or ignored, never failed
    perquisites: list = field(default_factory=list)  # (kind, period, rupees, document id) from payslips and Form 16
    orders: list = field(default_factory=list)       # smallcase orders from "Your smallcase order for <basket>" mail
    console_pnl: list = field(default_factory=list)  # (Console tax P&L statements, document id, modified time)
    itr_docs: list = field(default_factory=list)     # (income tax return document, document id, modified time)
    fidelity_docs: list = field(default_factory=list)  # (Fidelity statement, report or form, document id)
    more: bool = False                               # stopped at `limit` with documents left: the next call goes on


# (type, subject pattern, reason it is ignored, or None when a parser handles it). First match wins.
MAIL_TYPES = [
    ("smallcase_order", r"your smallcase order for", None),
    ("contract_note", r"contract note", None),
    ("cdsl_cas", r"consolidated account statement", None),
    ("coin_allotment", r"allotment report", None),
    ("coin_fidelity", r"restricted stock|rsu", None),
    ("coin_order", r"order placement", "order placed; the allotment report carries the units and NAV"),
    ("coin_sip", r"sip order", "SIP order list; the allotment report carries the units"),
    ("payment", r"payment success", "payment confirmation"),
    ("otp", r"otp|login from new device", "security mail"),
    ("margin", r"margin statement", "margin report; no trades"),
    ("commodity", r"commodit", "commodity account; not in the equity plan"),
    ("ledger", r"weekly (equity|account) statement|quarterly equity account|retention statement",
     "ledger statement: money movements, no trade lines"),
    ("demat_monthly", r"monthly demat transaction", "month-end demat movements; the CDSL statement carries the same"),
    ("settlement", r"quarterly settlement|maintenance charge|settlement of unused funds|account due for settlement",
     "account notice"),
    ("account_admin", r"account (got reset|credential)|login from new location|e-mail verification|bank account updat"
     r"|income range|client master|cmr copy|application forms?|payment failed|instant payout|password reset"
     r"|kite alerts|demat debit and pledge", "account administration; no trades"),
    ("company_notice", r"postal ballot|e-voting|annual general meeting|\bagm\b|annual report|dividend|financial result"
     r"|rights issue|court convened|intimation|general meeting|\begm\b|results|earning|posta ballot|revenue|mail from cdsl",
     "company notice to shareholders; no trades"),
    ("coin_redemption", r"redemption report", None),   # a fund sale
    ("bonus", r"bonus (shares|issue)|split shares|stock split|change in the company name",
     "corporate action; the corporate actions table carries it"),
    ("coin_update", r"coin by zerodha.{0,3}(order update|updates)|upcoming equity sips", "Coin order list or newsletter"),
    ("newsletter", r"smallcase and kite|free api|stock plans|tax resources|recertify|annual global statement",
     "newsletter or notice; no trades"),
    ("ipo_allotment", r"allotment received", None),   # IPO shares arrive with no contract note
    ("ipo", r"ipo application|allotment not received", "IPO application or refusal; the allotment mail carries any shares"),
]


# Drive files by name: (type, name pattern). Only the tradebook gives trades; the rest feed the tax lenses.
DRIVE_TYPES = [
    ("tradebook", r"tradebook.*\.csv$"),
    ("console_tax_pnl", r"taxpnl|p&l tax statement|profitloss"),
    ("form16", r"form ?16"),
    ("itr", r"itr|incometax(file|acknowledgement)|^[a-z]{5}\d{4}[a-z]-\d{4}\.pdf$"),
    ("payslip", r"payslip"),
    ("fidelity", r"fidelity|netbenefits|1042-s"),
    ("bank_statement", r"bank (account )?statement"),
    ("allocation_sheet", r"timeline|smallcap"),
    ("trade_details", r"trade_details"),
]


def classify_drive(item) -> str:
    name = item["name"].lower()
    return next((kind for kind, pattern in DRIVE_TYPES if re.search(pattern, name)), "unknown")


def classify_mail(item) -> tuple[str, str | None]:
    subject = item["subject"].lower()
    for name, pattern, reason in MAIL_TYPES:
        if re.search(pattern, subject):
            return name, reason
    return "unknown", None


def version(item) -> str:
    """What makes a document new: a Drive file changes when edited; a mail never does. Parser fixes count too."""
    return f"{item.get('modified', '')}|{PARSERS}"


def fetch(bridge, pan: str, since: str | None, isin_of=lambda name: None, done=frozenset(),
          limit: int | None = None) -> FeedResult:
    """`done` holds (id, version) pairs already handled; those documents are not downloaded again.
    `limit` caps the documents read in one call; `more` says some are left, and the next call takes them."""
    out = FeedResult()
    waiting = sorted(bridge.list(since=since or ALL_HISTORY), key=lambda i: i.get("date") or i.get("modified") or "")
    for item in waiting:      # oldest first: when the daily limit stops us, the newest are the ones left for tomorrow
        ident = item["id"]
        if (ident, version(item)) in done:
            continue
        if limit is not None and len(out.handled) + len(out.failed) + len(out.deferred) >= limit:
            out.more = True
            break
        before, before_pq, before_cp = len(out.trades), len(out.perquisites), len(out.console_pnl)
        before_itr, before_fd = len(out.itr_docs), len(out.fidelity_docs)
        try:
            verdict = _route(bridge, pan, item, out, isin_of)
        except google.Deferred:      # not read, not failed, not marked handled: the next sync tries it again
            out.trades, out.perquisites = out.trades[:before], out.perquisites[:before_pq]
            out.console_pnl = out.console_pnl[:before_cp]
            out.itr_docs, out.fidelity_docs = out.itr_docs[:before_itr], out.fidelity_docs[:before_fd]
            out.deferred.append(ident)
            continue
        except Exception as err:  # noqa: BLE001 - a malformed document must not stop the feed
            out.failed.append((ident, str(err)))
            continue
        if verdict is None:
            out.skipped.append(ident)
        elif verdict:
            out.ignored.append((ident, verdict))
        kind = classify_drive(item) if item["source"] == "drive" else classify_mail(item)[0]
        out.handled.append({"id": ident, "source": item["source"], "kind": kind,
                            "name": item.get("name") or item.get("subject", ""), "version": version(item),
                            "outcome": "unknown" if verdict is None else "ignored" if verdict else "parsed",
                            "reason": verdict or "", "trades": len(out.trades) - before})
    return out


def _route(bridge, pan, item, out, isin_of):
    """Returns "" when handled, a reason when ignored on purpose, None when nobody knows this document."""
    if item["source"] == "drive":
        return _route_drive(bridge, item, out, pan)
    ident = item["id"]
    kind, reason = classify_mail(item)
    if reason:
        return reason
    if kind in ("contract_note", "cdsl_cas"):
        pdfs = [a for a in item["attachments"]   # CDSL sends its PDFs as mime "bin"
                if a["mime"] == "application/pdf" or a.get("name", "").lower().endswith(".pdf")]
        if not pdfs:
            return "image attachment" if item["attachments"] else "no attachment"
        for a in pdfs[:1]:   # the first PDF is the document; later ones are annexes
            data = bridge.att(ident, a["i"]).data
            if kind == "contract_note":
                out.trades += contract_note.parse_pdf(data, pan)
            else:
                out.statements.append(cas.parse_pdf(data, pan))
        return ""
    if kind == "smallcase_order":
        day = date.fromisoformat((item.get("date") or "")[:10]) if item.get("date") else date.today()
        out.orders += smallcase.parse_order_mail(bridge.body(ident), item["subject"], day, ident)
        return ""
    if kind == "coin_allotment":
        out.trades += coin.parse_email(bridge.body(ident), isin_of)
        return ""
    if kind == "coin_redemption":
        day = date.fromisoformat(item["date"][:10]) if item.get("date") else date.today()
        out.trades += coin.parse_redemption(bridge.body(ident), day, isin_of)
        return ""
    if kind == "ipo_allotment":
        day = date.fromisoformat(item["date"][:10]) if item.get("date") else date.today()
        out.trades += ipo.parse_email(bridge.body(ident), item["subject"], day)
        return ""
    if kind == "coin_fidelity":
        trade = fidelity.parse_email(bridge.body(ident))
        if trade:
            out.trades.append(trade)
        return ""
    return None


def _route_drive(bridge, item, out, pan=""):
    name = item["name"].lower()
    kind = classify_drive(item)
    if kind in ("payslip", "form16") and name.endswith(".pdf"):
        text = pdftext.text(bridge.file(item["id"]).data, pan)
        found = rsu.parse_payslip(text) if kind == "payslip" else rsu.parse_form16(text)
        if not found:
            raise ValueError(f"{kind}: could not read the period and the RSU perquisite")
        out.perquisites.append((kind, found[0], found[1], item["id"]))
        return ""
    if kind == "console_tax_pnl" and name.endswith(".xlsx"):
        out.console_pnl.append((consolepnl.parse(bridge.file(item["id"]).data), item["id"], item.get("modified") or ""))
        return ""
    if kind in ("itr", "fidelity") and name.endswith(".pdf"):
        try:
            if kind == "itr":
                out.itr_docs.append((itr.parse_pdf(bridge.file(item["id"]).data, pan), item["id"], item.get("modified") or ""))
            else:
                out.fidelity_docs.append((fidelity_docs.parse_pdf(bridge.file(item["id"]).data, pan), item["id"]))
        except ValueError as err:
            if "password" in str(err):
                return "another password than the PAN opens it; not read"
            if "holdings export" in str(err):
                return str(err)
            raise
        return ""
    if name.endswith(".csv"):
        text = bridge.file(item["id"]).data.decode("utf-8-sig")
        if "trade_type" in text.splitlines()[0]:
            out.trades += tradebook.parse(text)
            return ""
        return "csv without trade rows"
    return None


def _norm(name: str) -> str:
    name = re.sub(r"\b(limited|ltd|pvt|private|the|india)\b\.?", " ", (name or "").lower())
    return "".join(c for c in name if c.isalnum())


def _name_ipo_shares(db, trades: list) -> list:
    """IPO mails name the company, not the ISIN: match the name to the NSE list (a unique match only). An IPO that
    matches nothing stays under its name, and a problem says so: no guess goes into the lots."""
    from stockpilot import journal
    listed = [(s, n, i) for s, n, i in db.execute("select symbol, name, isin from stocks where isin is not null").fetchall()]
    out = []
    for t in trades:
        if t.source == "ipo" and t.isin is None:
            want = _norm(t.symbol)
            hits = [(s, i) for s, n, i in listed if _norm(n) == want or _norm(s) == want]
            if len(hits) == 1:
                t = replace(t, symbol=hits[0][0], isin=hits[0][1])
            else:
                journal.problem(db, "trades", f"IPO allotment of {t.quantity:g} shares of {t.symbol} on {t.trade_date}: "
                                f"{'no listed stock has that name' if not hits else 'more than one stock has that name'}, "
                                "so it is not in the lots yet.", key=f"ipo:{t.symbol}")
        out.append(t)
    return out


def _price_of_now_inr(db):
    """ServiceNow's price in rupees around the 15th of a month, or None when the price or the rate is missing."""
    from stockpilot.sources import fx
    rate_on = fx.rate_on(db)

    def price(month: str):
        day = datetime.strptime(month, "%Y-%m").date().replace(day=15)
        row = db.execute("select close from prices where symbol = 'NOW' and exchange = 'NYSE' and date <= ? "
                         "order by date desc limit 1", [day]).fetchone()
        rate = rate_on(day)
        return row[0] * rate if row and row[0] and rate else None
    return price


def _store_perquisites(db, perquisites: list) -> None:
    """Payslip perquisites mark vest months: each becomes an expected vest (never a lot) unless a confirmed vest
    already sits in that month. Form 16 totals are checked against the payslips of that year."""
    from stockpilot import journal
    for kind, period, rupees, ref in perquisites:
        db.execute("insert or replace into payslip_perquisites values (?,?,?,?)", [kind, period, rupees, ref])
    slips = db.execute("select period, perquisite_inr from payslip_perquisites where kind = 'payslip' order by period").fetchall()
    confirmed = {d.strftime("%Y-%m") for (d,) in db.execute(
        "select trade_date from trades where side = 'vest' and status = 'confirmed'").fetchall()}
    price = _price_of_now_inr(db)
    usable, missing = [], []
    for month, perq in slips:
        if perq <= 0 or month in confirmed:
            continue
        (usable if price(month) else missing).append((month, perq))
    if usable:
        lots.save_trades(db, rsu.vests_from_payslips(usable, price))
    if missing:
        journal.problem(db, "trades", f"No ServiceNow price or dollar rate for {len(missing)} payslip months "
                        f"(from {missing[0][0]}), so their vests are not estimated.", key="rsu-payslip-price")
    for fy, total in db.execute("select period, perquisite_inr from payslip_perquisites where kind = 'form16'").fetchall():
        start = int(fy[:4])
        months = [f"{start}-{m:02d}" for m in range(4, 13)] + [f"{start + 1}-{m:02d}" for m in range(1, 4)]
        found = db.execute(f"select sum(perquisite_inr), count(*) from payslip_perquisites where kind = 'payslip' "
                           f"and period in ({', '.join('?' * 12)})", months).fetchone()
        if found[1] and abs(found[0] - total) > 0.05 * max(total, 1):
            journal.problem(db, "trades", f"Form 16 for {fy} shows RSU income of ₹{total:,.0f}; the payslips we have add up to "
                            f"₹{found[0]:,.0f}. Some payslips may be missing.", key=f"form16:{fy}")


def store_all(db, result: FeedResult) -> int:
    """Store parsed trades (new ones only) and return how many were added. Then tag every trade with who placed it,
    and turn payslip and Form 16 perquisites into expected vests."""
    added = lots.save_trades(db, _name_ipo_shares(db, result.trades))
    smallcase.save_orders(db, result.orders)
    smallcase.tag_trades(db)
    _store_perquisites(db, result.perquisites)
    for statements, ref, modified in result.console_pnl:
        consolepnl.save(db, statements, ref, modified)
    for doc, ref, modified in result.itr_docs:
        itr.save(db, doc, ref, modified)
    for doc, ref in result.fidelity_docs:
        fidelity_docs.save(db, doc, ref)
    return added
