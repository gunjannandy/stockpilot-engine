"""Fund NAV history, backfilled once and then kept by the nightly NAV job (R17).

`navs` held one row per scheme (the latest). The weekly fund review needs 3 years and the fund forecaster more, so this
loads five years for the schemes we need: every fund held, plus the Direct-plan Growth schemes in the same AMFI
categories (they are the peers). AMFI's history report cannot be filtered by scheme, so each response is streamed line by
line and only rows in scope are kept; nothing larger than one batch is ever in memory.

Resumable: each finished window is recorded in `fetch_log` (`navhistory:amfi:<scope id>`, period `from/to`). A restart,
or a later run, fetches only the days not covered. Inserts are `insert or replace` on the table's key, so repeats are safe.
If AMFI's report fails, mfapi.in is asked per scheme code for the same scope."""
import hashlib
import time
import urllib.request
from datetime import date, datetime, timedelta

HISTORY_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?frmdt={start}&todt={end}"
MFAPI_URL = "https://api.mfapi.in/mf/{code}"
USER_AGENT = "stockpilot-nav-history/1.0 (personal research tool; polite, one request at a time)"
YEARS = 5
WINDOW_DAYS = 45            # measured on the VM 2026-11-23: 90 days is refused, 45 and 30 answer; a refused window still halves
MIN_WINDOW_DAYS = 7
PAUSE_S = 3.0               # between AMFI calls
MFAPI_PAUSE_S = 1.0
RETRIES = (5, 20, 60)       # seconds waited before each retry of a failing call
BATCH = 5000
TARGET_YEARS = 3            # what the weekly review needs behind it
SOURCE = "navhistory:amfi"
MFAPI_SOURCE = "navhistory:mfapi"


def parse_day(text: str) -> date:
    return datetime.strptime(text, "%d-%b-%Y").date()


def day_text(day: date) -> str:
    return day.strftime("%d-%b-%Y")


# ---- scope --------------------------------------------------------------------------------------------------

def held_codes(db) -> list[int]:
    """Scheme codes of every fund we hold or have traded: lots, the latest holdings snapshot and trades, by ISIN."""
    return [c for (c,) in db.execute("""
        select distinct scheme_code from funds f where isin_growth in (select isin from (
            select isin from lots where lower(kind) in ('mf', 'fund')
            union select isin from trades where lower(kind) in ('mf', 'fund')
            union select isin from holdings where lower(kind) in ('mf', 'fund')
                and snapshot_at = (select max(snapshot_at) from holdings)) where isin is not null)
          or isin_reinvest in (select isin from (
            select isin from lots where lower(kind) in ('mf', 'fund')
            union select isin from trades where lower(kind) in ('mf', 'fund')) where isin is not null)
        order by 1""").fetchall()]


def scope(db) -> list[int]:
    """Held funds; every Direct/Growth scheme in the categories of held funds (the peers the review ranks against); and every
    Direct/Growth scheme in a researched group (fundgroups), so the owner can look for a fund to invest in."""
    from stockpilot import fundgroups
    held = held_codes(db)
    codes = set(held)
    if held:
        codes |= {c for (c,) in db.execute("""select scheme_code from funds where plan like 'Direct%' and option like '%Growth%'
            and category in (select category from funds where list_contains(?, scheme_code) and category is not null)""", [held]).fetchall()}
    codes |= {c for c, cat, name in db.execute("select scheme_code, category, name from funds where plan like 'Direct%' "
                                              "and option like '%Growth%'").fetchall() if fundgroups.group_of(cat, name)}
    return sorted(codes)


def scope_id(codes: list[int]) -> str:
    return hashlib.sha1(",".join(map(str, sorted(codes))).encode()).hexdigest()[:10]


# ---- parsing ------------------------------------------------------------------------------------------------

def parse_amfi(lines):
    """(date, scheme_code, nav) for each data row of AMFI's report: Scheme Code;NAV Name;Plan;Option;ISIN;ISIN;NAV;Date (checked against the real report, 2026-11-23).
    Header, category and AMC lines, and rows without a number ('N.A.'), are skipped."""
    for line in lines:
        parts = line.strip().split(";")
        if len(parts) < 8 or not parts[0].strip().isdigit():
            continue
        try:
            yield parse_day(parts[7].strip()), int(parts[0]), float(parts[6])
        except ValueError:
            continue


def _covered(db, source: str) -> list[tuple[date, date]]:
    out = []
    for (period,) in db.execute("select period from fetch_log where source = ?", [source]).fetchall():
        a, _, b = period.partition("/")
        try:
            out.append((date.fromisoformat(a), date.fromisoformat(b)))
        except ValueError:
            continue
    return sorted(out)


def missing(start: date, end: date, covered: list[tuple[date, date]]) -> list[tuple[date, date]]:
    """The stretches of [start, end] no finished window covers, oldest first."""
    gaps, cur = [], start
    for a, b in covered:
        if b < cur or a > end:
            continue
        if a > cur:
            gaps.append((cur, a - timedelta(days=1)))
        cur = max(cur, b + timedelta(days=1))
    if cur <= end:
        gaps.append((cur, end))
    return gaps


def _chunks(gap: tuple[date, date], size: int):
    s, end = gap
    while s <= end:
        e = min(s + timedelta(days=size - 1), end)
        yield s, e
        s = e + timedelta(days=1)


def _store(db, rows: list) -> None:
    """Rows in multi-row statements: DuckDB's executemany inserts one row at a time and is far too slow for tens of thousands."""
    for i in range(0, len(rows), 500):
        chunk = rows[i:i + 500]
        db.execute("insert or replace into navs values " + ",".join(["(?, ?, ?)"] * len(chunk)),
                   [v for row in chunk for v in row])


# ---- the AMFI report ----------------------------------------------------------------------------------------

class WindowFailed(Exception):
    pass


def _pull(db, open_lines, window, wanted: set[int], stats, sleep) -> None:
    """One window, streamed. Raises WindowFailed when AMFI errors or returns nothing readable."""
    url = HISTORY_URL.format(start=day_text(window[0]), end=day_text(window[1]))
    last = None
    for wait in (0, *RETRIES):
        if wait:
            sleep(wait)
        seen = kept = 0
        buf: list = []
        try:
            for row in parse_amfi(open_lines(url)):
                seen += 1
                if row[1] in wanted:
                    buf.append(row)
                    if len(buf) >= BATCH:
                        _store(db, buf)
                        kept += len(buf)
                        buf = []
            if buf:
                _store(db, buf)
                kept += len(buf)
        except (OSError, ValueError) as err:
            last = err
            continue
        stats["seen"] += seen
        stats["rows"] += kept
        if seen == 0:
            raise WindowFailed("AMFI returned no rows (a refused range reads as an empty or error page)")
        return
    raise WindowFailed(f"AMFI report failed: {last!r}")


def _window(db, open_lines, window, wanted, source, stats, sleep, min_days) -> bool:
    """Fetch a window; when AMFI refuses it, split it in half and try each half, down to `min_days`. True when all
    of it is stored and recorded."""
    try:
        _pull(db, open_lines, window, wanted, stats, sleep)
    except WindowFailed:
        days = (window[1] - window[0]).days + 1
        if days <= min_days:
            return False
        mid = window[0] + timedelta(days=days // 2 - 1)
        stats["shrunk"] += 1
        stats["size"] = min(stats["size"], days // 2)           # later windows start at the size that worked
        sleep(PAUSE_S)
        return (_window(db, open_lines, (window[0], mid), wanted, source, stats, sleep, min_days)
                and _window(db, open_lines, (mid + timedelta(days=1), window[1]), wanted, source, stats, sleep, min_days))
    db.execute("insert or replace into fetch_log values (?, ?)", [source, f"{window[0]}/{window[1]}"])
    stats["windows"] += 1
    return True


# ---- mfapi.in fallback --------------------------------------------------------------------------------------

def _mfapi(db, fetch_json, codes, floor: date, stats, sleep) -> None:
    for code in codes:
        key = f"{MFAPI_SOURCE}:{code}"
        if db.execute("select 1 from fetch_log where source = ?", [key]).fetchone():
            continue
        body = None
        for wait in (0, *RETRIES):
            if wait:
                sleep(wait)
            try:
                body = fetch_json(MFAPI_URL.format(code=code))
                break
            except (OSError, ValueError):
                continue
        if body is None:
            stats["failed"] += 1
            continue
        rows = []
        for p in (body or {}).get("data", []):
            try:
                d = datetime.strptime(p["date"], "%d-%m-%Y").date()
                if d >= floor:
                    rows.append((d, code, float(p["nav"])))
            except (KeyError, TypeError, ValueError):
                continue
        for i in range(0, len(rows), BATCH):
            _store(db, rows[i:i + BATCH])
        db.execute("insert or replace into fetch_log values (?, ?)", [key, str(date.today())])
        stats["fallback"] += 1
        stats["rows"] += len(rows)
        sleep(MFAPI_PAUSE_S)


# ---- the run ------------------------------------------------------------------------------------------------

def backfill(db, open_lines, fetch_json, today: date, start: date | None = None, window_days: int = WINDOW_DAYS,
             sleep=time.sleep, codes: list[int] | None = None, min_days: int = MIN_WINDOW_DAYS) -> dict:
    """Fill `navs` for the scope from `start` (default five years back) to `today`. Returns the counts."""
    stats = {"scope": 0, "windows": 0, "skipped": 0, "rows": 0, "seen": 0, "shrunk": 0, "failed": 0, "fallback": 0,
             "size": window_days}
    codes = scope(db) if codes is None else codes
    stats["scope"] = len(codes)
    if not codes:
        return stats
    start = start or today.replace(year=today.year - YEARS)
    source = f"{SOURCE}:{scope_id(codes)}"
    wanted = set(codes)
    covered = _covered(db, source)
    stats["skipped"] = sum(1 for _ in _chunks((start, today), window_days)) - sum(
        1 for g in missing(start, today, covered) for _ in _chunks(g, window_days))
    amfi_ok = True
    for gap in missing(start, today, covered):
        s = gap[0]
        while s <= gap[1] and amfi_ok:
            window = (s, min(s + timedelta(days=stats["size"] - 1), gap[1]))
            amfi_ok = _window(db, open_lines, window, wanted, source, stats, sleep, min_days)
            s = window[1] + timedelta(days=1)
            print(f"navs-history: {window[0]} to {window[1]} done, {stats['rows']} rows kept so far", flush=True)
            sleep(PAUSE_S)
        if not amfi_ok:
            break
    if not amfi_ok and fetch_json is not None:
        _mfapi(db, fetch_json, codes, start, stats, sleep)
    elif not amfi_ok:
        stats["failed"] += 1
    return stats


def probe(open_lines, today: date, sizes=(30, 90, 180, 365, 730), sleep=time.sleep) -> dict:
    """Which window sizes AMFI answers with a full span of dates: {days: True/False}. Run on the VM; the answer goes
    into docs/research/data-sources.md and `WINDOW_DAYS`."""
    out = {}
    for size in sizes:
        end = today - timedelta(days=7)
        start = end - timedelta(days=size - 1)
        try:
            days = {d for d, _, _ in parse_amfi(open_lines(HISTORY_URL.format(start=day_text(start), end=day_text(end))))}
        except (OSError, ValueError):
            days = set()
        out[size] = bool(days) and (end - min(days)).days >= size - 8        # the oldest day returned is near the start asked
        sleep(PAUSE_S)
    return out


# ---- readiness ----------------------------------------------------------------------------------------------

def gaps(db, today: date) -> list[str]:
    """One line for the Health tab when a held fund has under 3 years of NAVs: the date the shortest history reaches back to."""
    cutoff = today.replace(year=today.year - TARGET_YEARS) + timedelta(days=10)    # the review's tolerance
    short = []
    for code in held_codes(db):
        first = db.execute("select min(date) from navs where scheme_code = ?", [code]).fetchone()[0]
        if first is None or first > cutoff:
            short.append((first or date.max, code))
    if not short:
        return []
    first, code = max(short)
    name = db.execute("select name from funds where scheme_code = ?", [code]).fetchone()[0]
    more = f" (and {len(short) - 1} more held fund{'s' if len(short) > 2 else ''})" if len(short) > 1 else ""
    return [f"Fund NAV history reaches back only {first if first != date.max else 'nowhere'} for {name}{more}; "
            "the fund review needs 3 years (run `sp navs-history`)."]


# ---- the real fetchers --------------------------------------------------------------------------------------

def open_lines(url: str, timeout: int = 120):
    """Stream a response line by line (nothing is read ahead beyond the socket buffer)."""
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    resp = urllib.request.urlopen(req, timeout=timeout)

    def lines():
        with resp:
            for raw in resp:
                yield raw.decode("utf-8", errors="replace")
    return lines()


def fetch_json(url: str, timeout: int = 60):
    import json
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.load(resp)
