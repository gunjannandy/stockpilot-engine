"""Promoter holding and pledge, quarterly, from NSE's shareholding master (one call a stock: every filing, with the
promoter-group percentage) and the shareholding XBRL each filing links to (the pledge). Stocks with a pane only: held,
watched, or on the newest calls. A quarter is read once; a revised filing replaces its quarter; an XBRL that fails keeps
the promoter number and is retried on the next run. The job runs in working hours (see due.py)."""
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date

from stockpilot import journal
from stockpilot.sources import insert, nse_date, number, transaction

MASTER = "/api/corporate-share-holdings-master?index=equities&symbol={}"
KEEP_QUARTERS = 5
MAX_XBRL_BYTES = 3_000_000
PROMOTER_MEMBER = "PromoterAndPromoterGroupMember"
PROMOTER_PCT = "ShareholdingAsAPercentageOfTotalNumberOfShares"
# Real files (checked 2026-11-24 on JIOFIN and KARURVYSYA): values are fractions (0.0465 = 4.65%), the pledge is
# "EncumberedShareUnderPledged..." as a share of the promoter group's own shares, and a company with no pledge has no
# number at all, only a false flag. The invented fixtures use percent and the old name; both stay readable.
PLEDGE_PCT = "PercentageOfSharesPledgedOrOtherwiseEncumbered"
PLEDGE_PCT_REAL = "EncumberedShareUnderPledgedAsPercentageOfTotalNumberOfShares"
PLEDGE_FLAG = "WhetherAnySharesHeldByPromotersAreEncumberedUnderPledgedForPromoterAndPromoterGroup"


@dataclass(frozen=True)
class Filing:
    symbol: str
    quarter_end: date
    promoter_pct: float
    public_pct: float | None
    xbrl_url: str | None
    filed_on: date | None


def parse_master(data) -> list[Filing]:
    """One filing per quarter, newest first; where a quarter was filed twice the later submission wins."""
    rows = data.get("data") if isinstance(data, dict) else data
    best: dict = {}
    for r in rows or []:
        try:
            quarter, promoter = nse_date(r.get("date")), number(r.get("pr_and_prgrp"))
            filed = nse_date((r.get("submissionDate") or "")[:11].strip() or None)
        except (ValueError, AttributeError):
            continue
        if not r.get("symbol") or quarter is None or promoter is None:
            continue
        f = Filing(r["symbol"], quarter, promoter, number(r.get("public_val")), r.get("xbrl") or None, filed)
        cur = best.get((f.symbol, quarter))
        if cur is None or (f.filed_on or date.min) >= (cur.filed_on or date.min):
            best[(f.symbol, quarter)] = f
    return sorted(best.values(), key=lambda f: f.quarter_end, reverse=True)


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def parse_xbrl(raw: bytes) -> dict:
    """The promoter group's total holding and its pledged share, from the context tagged as the promoter group.
    A missing element is None (unknown), never 0."""
    out = {"promoter_pct": None, "pledge_pct": None}
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return out
    promoter_contexts = set()
    for ctx in root.iter():
        if _local(ctx.tag) == "context":
            for member in ctx.iter():
                if _local(member.tag) == "explicitMember" and (member.text or "").strip().endswith(PROMOTER_MEMBER):
                    promoter_contexts.add(ctx.get("id"))
    real = False                   # fractions (decimals="INF"), not the invented fixtures' percent
    flag_false = False
    for el in root.iter():
        name = _local(el.tag)
        if name == PLEDGE_FLAG and (el.text or "").strip().lower() == "false":
            flag_false = True
        if el.get("contextRef") in promoter_contexts:
            key = {PROMOTER_PCT: "promoter_pct", PLEDGE_PCT: "pledge_pct", PLEDGE_PCT_REAL: "pledge_pct"}.get(name)
            if key and out[key] is None:
                out[key] = number(el.text)
                real = real or el.get("decimals") == "INF"
    if real:
        out = {k: None if v is None else round(v * 100, 4) for k, v in out.items()}
    if out["pledge_pct"] is None and flag_false and out["promoter_pct"] is not None:
        out["pledge_pct"] = 0.0    # the company states in the filing that none is pledged
    return out


def pane_symbols(db) -> list[str]:
    rows = db.execute("""
        select symbol from holdings where kind = 'stock' and snapshot_at = (select max(snapshot_at) from holdings)
        union select symbol from watchlist where removed_at is null
        union select symbol from calls where made_on = (select max(made_on) from calls)
        order by symbol""").fetchall()
    return [s for s, in rows if s]


def _store_filings(db, symbol: str, filings: list[Filing]) -> int:
    """Insert new quarters; replace a quarter whose filing changed (a revision), which asks for its pledge again."""
    changed = 0
    for f in filings:
        old = db.execute("select xbrl_url, filed_on from ownership where symbol = ? and quarter_end = ?",
                         [symbol, f.quarter_end]).fetchone()
        if old and old == (f.xbrl_url, f.filed_on):
            continue
        db.execute("insert or replace into ownership values (?, ?, ?, ?, null, ?, ?, ?)",
                   [symbol, f.quarter_end, f.promoter_pct, f.public_pct, f.xbrl_url, f.filed_on, f.xbrl_url is None])
        changed += 1
    return changed


def ingest(db, symbols, fetch_json, fetch_file, keep: int = KEEP_QUARTERS) -> dict:
    """Master first (one call a stock), then the XBRL of each stored quarter whose pledge is not yet read.
    One stock failing is counted and skipped; every stock failing raises (NSE is blocking us)."""
    totals = {"symbols": 0, "quarters": 0, "pledge_read": 0, "failed": 0}
    master_failed = 0
    for symbol in symbols:
        try:
            filings = [f for f in parse_master(fetch_json(MASTER.format(symbol))) if f.symbol == symbol][:keep]
        except Exception:  # noqa: BLE001 - a bad reply for one stock must not stop the others
            master_failed += 1
            totals["failed"] += 1
            continue
        totals["symbols"] += 1
        with transaction(db):
            _store_filings(db, symbol, filings)
        keep_from = filings[-1].quarter_end if filings else None
        totals["quarters"] += len(filings)
        pending = db.execute("select quarter_end, xbrl_url from ownership where symbol = ? and not pledge_checked and quarter_end >= ? "
                             "order by quarter_end desc", [symbol, keep_from or date.min]).fetchall() if filings else []
        for quarter, url in pending:
            try:
                raw = fetch_file(url, MAX_XBRL_BYTES)
            except Exception:  # noqa: BLE001
                totals["failed"] += 1
                continue
            if raw is None:
                totals["failed"] += 1
                continue
            got = parse_xbrl(raw)
            db.execute("update ownership set pledge_pct = ?, pledge_checked = true, promoter_pct = coalesce(promoter_pct, ?) "
                       "where symbol = ? and quarter_end = ?", [got["pledge_pct"], got["promoter_pct"], symbol, quarter])
            totals["pledge_read"] += 1
    if symbols and master_failed == len(symbols):
        raise RuntimeError(f"NSE's shareholding master answered for none of {len(symbols)} stocks")
    return totals


def run(m, now, force: bool = False) -> dict:
    with m.db("ownership") as db:
        symbols = pane_symbols(db)
        try:
            counts = journal.tracked(db, "ownership", lambda: ingest(db, symbols, db.releasing(m.fetch_json), db.releasing(m.fetch_file)))
        except Exception as err:  # noqa: BLE001 - journal.run has logged it; the tick carries on
            return {"status": "failed", "error": str(err)}
    return {"status": "ok", **counts}
