"""The index of quarterly financial-results filings. Stored only; the XBRL behind each link is parsed later."""
from datetime import date, datetime

import duckdb

from stockpilot.sources import insert, nse_date

PATH = "/api/corporates-financial-results?index=equities&period=Quarterly"


def _filed_at(f: dict) -> datetime | None:
    for key, fmt in (("filingDate", "%d-%b-%Y %H:%M"), ("broadCastDate", "%d-%b-%Y %H:%M:%S")):
        try:
            return datetime.strptime(f[key], fmt)
        except (KeyError, TypeError, ValueError):
            continue
    return None


def ingest(db: duckdb.DuckDBPyConnection, day: date, fetch_json) -> int:
    rows = []
    for f in fetch_json(PATH) or []:
        start, end, filed = nse_date(f.get("fromDate")), nse_date(f.get("toDate")), _filed_at(f)
        if not (f.get("symbol") and start and end and filed):
            continue
        link = f.get("xbrl")
        has_link = bool(link) and not link.rstrip().endswith("/-")   # NSE puts a bare '-' where there is no file
        rows.append((f.get("isin"), f["symbol"], start, end, f.get("consolidated") == "Consolidated",
                     f.get("audited") == "Audited", filed, link if has_link else None))
    insert(db, "insert or replace into filings_index values (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return len(rows)


# ---- R9: quarterly numbers from the XBRL behind each filing -------------------------------------------------

import re
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import timedelta

from stockpilot.sources import insert

MAX_BYTES = 2 * 1024 * 1024             # a bigger file is skipped (standalone filings of big companies run to MB)
KEEP = 12                               # quarters per company on backfill
REFRESH_KEEP = 4
OLD_FEED = "/api/corporates-financial-results?index=equities&symbol={}&period=Quarterly"
NEW_FEED = ("/api/integrated-filing-results?index=equities&symbol={}&period_ended=all"
            "&type=Integrated%20Filing-%20Financials")

# Tag names are the same across the old `in-bse-fin` and the 2025 `in-capmkt` namespaces; we match on the local
# name. First tag found wins. Banks tag interest earned instead of revenue and their own EPS names.
REVENUE = ("RevenueFromOperations", "InterestEarned", "Income")
OPERATING_PROFIT = ("OperatingProfit", "OperatingProfitBeforeProvisionAndContingencies")
NET_PROFIT = ("ProfitLossForPeriod", "ProfitLossForThePeriod")
EPS = ("BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations", "BasicEarningsPerShareAfterExtraordinaryItems",
       "BasicEarningsLossPerShareFromContinuingOperations", "BasicEarningsPerShareBeforeExtraordinaryItems")
_WANTED = {t: None for group in (REVENUE, OPERATING_PROFIT, NET_PROFIT, EPS) for t in group}


def size_bytes(text) -> float | None:
    """'120.97 KB' -> bytes, from the size NSE prints in the integrated index. None when unknown."""
    m = re.fullmatch(r"\s*([\d.,]+)\s*(bytes|kb|mb|gb)\s*", str(text or ""), re.I)
    if not m:
        return None
    return float(m.group(1).replace(",", "")) * {"bytes": 1, "kb": 1024, "mb": 1024 ** 2, "gb": 1024 ** 3}[m.group(2).lower()]


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def parse_xbrl(raw: bytes) -> dict | None:
    """The 3-month numbers of one results file: {period_end, revenue, operating_profit, net_profit, eps}, or None
    when it is not a results file. Contexts are read from the file (their ids are not trusted) and only a context
    of about three months counts, so the year-to-date column is never used."""
    if b"<!DOCTYPE" in raw[:2048].upper() or b"<!ENTITY" in raw.upper():
        return None                         # no DTDs: nothing legitimate needs one, and it blocks entity bombs
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return None
    quarter = {}                            # context id -> period end, for 3-month contexts only
    for ctx in root.iter():
        if _local(ctx.tag) != "context":
            continue
        start = end = None
        for el in ctx.iter():
            if _local(el.tag) == "startDate":
                start = el.text
            elif _local(el.tag) == "endDate":
                end = el.text
        try:
            s, e = date.fromisoformat(start.strip()), date.fromisoformat(end.strip())
        except (AttributeError, ValueError):
            continue
        if 80 <= (e - s).days <= 100:
            quarter[ctx.get("id")] = e
    found: dict[str, dict] = {}             # tag -> period end -> value
    for el in root.iter():
        name = _local(el.tag)
        end = quarter.get(el.get("contextRef"))
        if name in _WANTED and end and (el.text or "").strip():
            try:
                found.setdefault(name, {}).setdefault(end, float(el.text.strip().replace(",", "")))
            except ValueError:
                pass
    ends = {e for by_end in found.values() for e in by_end}
    if not ends:
        return None
    period_end = max(ends)

    def pick(tags):
        return next((found[t][period_end] for t in tags if period_end in found.get(t, {})), None)

    out = {"period_end": period_end, "revenue": pick(REVENUE), "operating_profit": pick(OPERATING_PROFIT),
           "net_profit": pick(NET_PROFIT), "eps": pick(EPS)}
    return out if out["revenue"] is not None or out["net_profit"] is not None else None


def fetchers(session):
    """(fetch_json, fetch_file) on one NSE session, so both share its cookies and its 1.1 s spacing.
    fetch_file(url, max_bytes) -> bytes, or None when the file is bigger than max_bytes."""
    def fetch_file(url: str, max_bytes: int = MAX_BYTES):
        wait = 1.1 - (time.time() - session._last)
        if wait > 0:
            time.sleep(wait)
        session._last = time.time()
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.nseindia.in/"})
        with session._opener.open(req, timeout=30) as resp:
            body = resp.read(max_bytes + 1)
        return None if len(body) > max_bytes else body
    return session.fetch_json, fetch_file


def _candidates(old_rows, new_rows) -> list[dict]:
    """One filing per quarter: consolidated if there is one, else standalone; the latest filing of that kind."""
    best: dict = {}
    for r in list(new_rows) + list(old_rows):
        if r["cumulative"]:
            continue
        key = r["period_end"]
        cur = best.get(key)
        if cur is None or (r["consolidated"], r["filed_at"]) > (cur["consolidated"], cur["filed_at"]):
            best[key] = r
    return [best[k] for k in sorted(best, reverse=True)]


def _old_rows(rows):
    for f in rows or []:
        end, filed = nse_date(f.get("toDate")), _filed_at(f)
        url = f.get("xbrl")
        if f.get("symbol") and end and filed and url and not url.rstrip().endswith("/-"):
            yield {"isin": f.get("isin"), "period_end": end, "consolidated": f.get("consolidated") == "Consolidated",
                   "filed_at": filed, "url": url, "size": None,
                   "cumulative": f.get("cumulative", "").lower() == "cumulative"}


def _new_rows(blob):
    for f in (blob or {}).get("data", []) if isinstance(blob, dict) else []:
        try:
            end = datetime.strptime(f["qe_Date"].title(), "%d-%b-%Y").date()
            filed = datetime.strptime(f.get("broadcast_Date") or f["creation_Date"], "%d-%b-%Y %H:%M:%S")
        except (KeyError, TypeError, ValueError):
            continue
        if f.get("xbrl"):
            yield {"isin": None, "period_end": end, "consolidated": f.get("consolidated") == "Consolidated",
                   "filed_at": filed, "url": f["xbrl"], "size": size_bytes(f.get("xbrlFileSize")), "cumulative": False}


def _load(db, symbol, fetch_json, fetch_file, keep, totals) -> bool:
    """Fetch and store the newest `keep` quarters of one company. True when nothing failed. An index failure
    raises (NSE is blocking us; the run stops and the next run resumes)."""
    rows = _candidates(_old_rows(fetch_json(OLD_FEED.format(symbol))), _new_rows(fetch_json(NEW_FEED.format(symbol))))
    clean = True
    for r in rows[:keep]:
        if db.execute("select 1 from quarterly where symbol = ? and source_url = ?", [symbol, r["url"]]).fetchone():
            continue
        if r["size"] is not None and r["size"] > MAX_BYTES:
            totals["too_big"] += 1
            continue
        try:
            raw = fetch_file(r["url"], MAX_BYTES)
        except Exception:
            totals["failed"] += 1
            clean = False
            continue
        if raw is None:
            totals["too_big"] += 1
            continue
        q = parse_xbrl(raw)
        if q is None:
            totals["unreadable"] += 1
            continue
        insert(db, "insert or replace into quarterly values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
               [(r["isin"] or _isin(db, symbol), symbol, q["period_end"], r["consolidated"], r["filed_at"], q["revenue"],
                 q["operating_profit"], q["net_profit"], q["eps"], r["url"])])
        totals["stored"] += 1
    return clean


def _isin(db, symbol):
    row = db.execute("select isin from stocks where symbol = ? and isin is not null limit 1", [symbol]).fetchone() \
        or db.execute("select isin from filings_index where symbol = ? and isin is not null limit 1", [symbol]).fetchone()
    return row[0] if row else None


def _totals():
    return {"stored": 0, "failed": 0, "too_big": 0, "unreadable": 0, "skipped_done": 0, "companies": 0}


def backfill(db, fetch_json, fetch_file, symbols, today: date, keep: int = KEEP) -> dict:
    """The newest `keep` quarters per company, in the order given. A company finished is recorded in `fetch_log`
    as `filings:<SYMBOL>` and skipped next run; one that had a failed download is retried (what was stored is
    not fetched again)."""
    totals = _totals()
    for symbol in symbols:
        source = f"filings:{symbol}"
        if db.execute("select 1 from fetch_log where source = ?", [source]).fetchone():
            totals["skipped_done"] += 1
            continue
        totals["companies"] += 1
        if _load(db, symbol, fetch_json, fetch_file, keep, totals):
            db.execute("insert or replace into fetch_log values (?, ?)", [source, today.isoformat()])
    return totals


def refresh(db, fetch_json, fetch_file, symbols, today: date) -> dict:
    """The weekly top-up: only companies already backfilled whose results date (from the results calendar) has
    passed since the last filing we hold."""
    totals = _totals()
    for symbol in symbols:
        if not db.execute("select 1 from fetch_log where source = ?", [f"filings:{symbol}"]).fetchone():
            continue                        # not backfilled yet: the backfill's job
        due = db.execute("""select 1 from results_calendar c where c.symbol = ? and c.date <= ?
            and c.date > coalesce((select max(cast(filed_at as date)) from quarterly q where q.symbol = c.symbol),
                                  date '1900-01-01')""", [symbol, today]).fetchone()
        if due:
            totals["companies"] += 1
            _load(db, symbol, fetch_json, fetch_file, REFRESH_KEEP, totals)
    return totals


def history(db, symbol: str, as_of, n: int = 8) -> list[dict]:
    """The last `n` quarters of `symbol` as they were known at `as_of` (`filed_at <= as_of`; a plain date covers
    that whole day). Newest first; consolidated over standalone; a restated quarter shows its latest filing then."""
    if not isinstance(as_of, datetime):
        as_of = datetime.combine(as_of, datetime.min.time()) + timedelta(days=1) - timedelta(microseconds=1)
    cols = ["isin", "symbol", "period_end", "consolidated", "filed_at", "revenue", "operating_profit", "net_profit",
            "eps", "source_url"]
    rows = db.execute(f"""select {', '.join(cols)} from quarterly where symbol = ? and filed_at <= ?
        qualify row_number() over (partition by period_end order by consolidated desc, filed_at desc) = 1
        order by period_end desc limit ?""", [symbol, as_of, n]).fetchall()
    return [dict(zip(cols, r)) for r in rows]


def symbols_to_load(db, today: date, floor: float = 1.0) -> list[str]:
    """Holdings first, then the watchlist, then the rest of the liquid pool (the pool already holds the watchlist)."""
    from stockpilot.sources import fundamentals
    held = [s for (s,) in db.execute("""select symbol from holdings where kind = 'stock'
        and snapshot_at = (select max(snapshot_at) from holdings) order by symbol""").fetchall()]
    watch = [s for (s,) in db.execute("select distinct symbol from watchlist where removed_at is null order by symbol"
                                      ).fetchall()]
    out: list[str] = []
    for s in held + watch + fundamentals.pool(db, today, floor):
        if s not in out:
            out.append(s)
    return out
