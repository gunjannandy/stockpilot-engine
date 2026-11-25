"""All-time daily price history for every NSE and BSE stock (SME included, delisted kept), as Parquet files by exchange
and year. Public market files only; nothing private. Built to run on public Actions and attach the files to a release.

Files in the store directory:
  prices-{NSE|BSE}-{year}.parquet   one row per stock per day, sorted by ISIN then date, zstd
  checked-{NSE|BSE}-{year}.parquet  every day we asked the exchange about, with its row count (0 = holiday or not published)
  corporate_actions.parquet         splits, bonuses and dividends parsed from NSE's own subjects
  isin_map.parquet                  symbol (NSE) or scrip code (BSE) -> symbol, ISIN and the dates seen
  report.json                       rows per exchange and year

Prices are stored raw and unadjusted; the adjustment factor comes from corporate_actions at read time. Every download
goes through `fetch(url) -> bytes | None` (None = no file, 404), so tests serve saved files and production serves HTTP."""
import io
import json
import re
import time
import zipfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

from stockpilot.sources.http import fetch as http_fetch
from stockpilot.sources.marketdata import BSE_STOCK_GROUPS, STOCK_SERIES

NSE_ARCHIVES = "https://nsearchives.nseindia.com"
BSE_DOWNLOAD = "https://www.bseindia.com/download/BhavCopy/Equity"
NSE_LEGACY_LAST = date(2024, 7, 5)          # last legacy file; UDiFF starts 2024-01-02 (the two overlap)
NSE_UDIFF_FROM = date(2024, 7, 8)           # we read UDiFF from the day after the last legacy file
NSE_FIRST_DAY = date(1994, 11, 3)
BSE_FIRST_DAY = date(2006, 9, 1)            # real start is at or before this; earlier days answer with the HTML stub
BSE_UDIFF_FROM = date(2024, 7, 8)
SERIES = STOCK_SERIES | {"SZ"}              # main board EQ BE BZ, SME SM ST SZ; bonds, G-secs and the rest are not stocks
EXCHANGES = ("NSE", "BSE")
IST = timezone(timedelta(hours=5, minutes=30))

COLUMNS = [("exchange", "VARCHAR"), ("symbol", "VARCHAR"), ("code", "VARCHAR"), ("series", "VARCHAR"),
           ("isin", "VARCHAR"), ("date", "DATE"), ("open", "DOUBLE"), ("high", "DOUBLE"), ("low", "DOUBLE"),
           ("close", "DOUBLE"), ("prev_close", "DOUBLE"), ("volume", "BIGINT"), ("trades", "BIGINT"),
           ("value", "DOUBLE"), ("source", "VARCHAR")]
NAMES = [c for c, _ in COLUMNS]
DDL = ", ".join(f"{c} {t}" for c, t in COLUMNS)
ORDER = "isin nulls last, coalesce(symbol, code), date"


# ---- URLs -------------------------------------------------------------------------------------------------------

def nse_url(day: date) -> str:
    if day >= NSE_UDIFF_FROM:
        return f"{NSE_ARCHIVES}/content/cm/BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"
    mon = day.strftime("%b").upper()
    return f"{NSE_ARCHIVES}/content/historical/EQUITIES/{day.year}/{mon}/cm{day:%d}{mon}{day.year}bhav.csv.zip"


def bse_url(day: date) -> str:
    if day >= BSE_UDIFF_FROM:
        return f"{BSE_DOWNLOAD}/BhavCopy_BSE_CM_0_0_0_{day:%Y%m%d}_F_0000.CSV"
    return f"{BSE_DOWNLOAD}/EQ{day:%d%m%y}_CSV.ZIP"


URLS = {"NSE": nse_url, "BSE": bse_url}


# ---- parsing one day's file -------------------------------------------------------------------------------------

def _num(text):
    text = (text or "").strip()
    try:
        return float(text) if text else None
    except ValueError:
        return None


def _int(text):
    n = _num(text)
    return None if n is None else int(n)


def _csv_rows(text: str):
    import csv
    reader = csv.DictReader(io.StringIO(text))
    reader.fieldnames = [f.strip() for f in reader.fieldnames or []]
    return reader


def _unzip_text(blob: bytes) -> str | None:
    if not blob or not zipfile.is_zipfile(io.BytesIO(blob)):
        return None
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        return zf.read(zf.namelist()[0]).decode("utf-8-sig", errors="replace")


def _row(exchange, day, source, **kw):
    r = dict.fromkeys(NAMES)
    r.update(exchange=exchange, date=day, source=source, **kw)
    return r


def parse_nse(blob: bytes | None, day: date) -> list[dict]:
    """One NSE bhavcopy (legacy or UDiFF, a zip) as rows for stocks only. A missing or non-zip answer gives no rows."""
    text = _unzip_text(blob) if blob else None
    if text is None:
        return []
    rows = []
    for r in _csv_rows(text):
        if "TckrSymb" in r:                                   # UDiFF
            if (r.get("FinInstrmTp") or "").strip() != "STK" or (r.get("SctySrs") or "").strip() not in SERIES:
                continue
            rows.append(_row("NSE", day, "nse", symbol=r["TckrSymb"].strip(), series=r["SctySrs"].strip(),
                             isin=(r.get("ISIN") or "").strip() or None, open=_num(r["OpnPric"]), high=_num(r["HghPric"]),
                             low=_num(r["LwPric"]), close=_num(r["ClsPric"]), prev_close=_num(r["PrvsClsgPric"]),
                             volume=_int(r["TtlTradgVol"]), trades=_int(r.get("TtlNbOfTxsExctd")),
                             value=_num(r["TtlTrfVal"])))
        else:                                                 # legacy, 1994 to 2024-07-05
            if (r.get("SERIES") or "").strip() not in SERIES:
                continue
            rows.append(_row("NSE", day, "nse", symbol=r["SYMBOL"].strip(), series=r["SERIES"].strip(),
                             isin=(r.get("ISIN") or "").strip() or None, open=_num(r["OPEN"]), high=_num(r["HIGH"]),
                             low=_num(r["LOW"]), close=_num(r["CLOSE"]), prev_close=_num(r.get("PREVCLOSE")),
                             volume=_int(r.get("TOTTRDQTY")), trades=_int(r.get("TOTALTRADES")),
                             value=_num(r.get("TOTTRDVAL"))))
    return rows


def parse_bse(blob: bytes | None, day: date) -> list[dict]:
    """One BSE bhavcopy: a zip before mid-2024, a plain CSV after. A missing day comes back as an HTML page with status
    200, so the content is checked, never the status: anything that is neither a zip nor a UDiFF CSV gives no rows."""
    if not blob:
        return []
    if blob[:2] == b"PK":
        text = _unzip_text(blob)
    elif b"FinInstrmTp" in blob[:2000]:
        text = blob.decode("utf-8-sig", errors="replace")
    else:
        return []
    if text is None:
        return []
    rows = []
    for r in _csv_rows(text):
        if "TckrSymb" in r:                                   # UDiFF
            grp = (r.get("SctySrs") or "").strip()
            if (r.get("FinInstrmTp") or "").strip() != "STK" or grp not in BSE_STOCK_GROUPS:
                continue
            rows.append(_row("BSE", day, "bse", symbol=r["TckrSymb"].strip(), code=(r.get("FinInstrmId") or "").strip(),
                             series=grp, isin=(r.get("ISIN") or "").strip() or None, open=_num(r["OpnPric"]),
                             high=_num(r["HghPric"]), low=_num(r["LwPric"]), close=_num(r["ClsPric"]),
                             prev_close=_num(r["PrvsClsgPric"]), volume=_int(r["TtlTradgVol"]),
                             trades=_int(r.get("TtlNbOfTxsExctd")), value=_num(r["TtlTrfVal"])))
        else:                                                 # legacy: scrip code, name, group; no symbol, no ISIN
            grp = (r.get("SC_GROUP") or "").strip()
            if grp not in BSE_STOCK_GROUPS or not (r.get("SC_CODE") or "").strip():
                continue
            rows.append(_row("BSE", day, "bse", code=r["SC_CODE"].strip(), series=grp, open=_num(r["OPEN"]),
                             high=_num(r["HIGH"]), low=_num(r["LOW"]), close=_num(r["CLOSE"]),
                             prev_close=_num(r.get("PREVCLOSE")), volume=_int(r.get("NO_OF_SHRS")),
                             trades=_int(r.get("NO_TRADES")), value=_num(r.get("NET_TURNOV"))))
    return rows


PARSERS = {"NSE": parse_nse, "BSE": parse_bse}


# ---- the store --------------------------------------------------------------------------------------------------

def _q(path) -> str:
    return str(path).replace("'", "''")


class HistoryStore:
    def __init__(self, directory):
        self.dir = Path(directory)
        self.dir.mkdir(parents=True, exist_ok=True)

    # -- file helpers
    def _prices(self, exchange, year) -> Path:
        return self.dir / f"prices-{exchange}-{year}.parquet"

    def _checked(self, exchange, year) -> Path:
        return self.dir / f"checked-{exchange}-{year}.parquet"

    def price_files(self, exchange=None) -> list[Path]:
        return sorted(self.dir.glob(f"prices-{exchange or '*'}-*.parquet"))

    def _write(self, con, table, path, order):
        tmp = path.with_suffix(".tmp")
        con.execute(f"copy (select * from {table} order by {order}) to '{_q(tmp)}' "
                    "(format parquet, compression zstd, row_group_size 122880)")
        tmp.replace(path)

    def _open_year(self, exchange, year):
        con = duckdb.connect()
        con.execute(f"create table t ({DDL})")
        path = self._prices(exchange, year)
        if path.exists():
            con.execute(f"insert into t select {', '.join(NAMES)} from read_parquet('{_q(path)}')")
        return con

    @staticmethod
    def _insert(con, rows):
        if rows:
            con.executemany(f"insert into t values ({', '.join('?' * len(NAMES))})",
                        [tuple(r[n] for n in NAMES) for r in rows])

    # -- days asked
    def rows_for(self, exchange, day) -> int | None:
        """Rows we stored for a day, 0 for a day the exchange had no file, None for a day never asked."""
        path = self._checked(exchange, day.year)
        if not path.exists():
            return None
        got = duckdb.execute(f"select rows from read_parquet('{_q(path)}') where date = ?", [day]).fetchone()
        return None if got is None else got[0]

    def is_checked(self, exchange, day) -> bool:
        return self.rows_for(exchange, day) is not None

    def _mark(self, exchange, year, counts: dict):
        path = self._checked(exchange, year)
        con = duckdb.connect()
        con.execute("create table c (exchange varchar, date date, rows bigint)")
        if path.exists():
            con.execute(f"insert into c select exchange, date, rows from read_parquet('{_q(path)}')")
        for day in counts:
            con.execute("delete from c where date = ?", [day])
        if counts:
            con.executemany("insert into c values (?, ?, ?)", [(exchange, d, n) for d, n in counts.items()])
        self._write(con, "c", path, "date")

    # -- adding days
    def append_days(self, exchange, days: dict[date, list[dict]]) -> int:
        """Store several days (all in one calendar year per call group) with one rewrite per year file. A day already
        stored is replaced, so running it again changes nothing. Returns rows written."""
        by_year: dict[int, dict[date, list[dict]]] = {}
        for day, rows in days.items():
            by_year.setdefault(day.year, {})[day] = rows
        total = 0
        for year, chunk in sorted(by_year.items()):
            new_rows = [r for rows in chunk.values() for r in rows]
            if new_rows:
                con = self._open_year(exchange, year)
                symbols = [r["symbol"] for r in new_rows if r["symbol"]]
                for day in chunk:                              # the exchange's own file beats a Yahoo gap-fill
                    con.execute("delete from t where date = ? and (source <> 'yahoo' or symbol = any(?))", [day, symbols])
                self._insert(con, new_rows)
                self._write(con, "t", self._prices(exchange, year), ORDER)
                total += len(new_rows)
            self._mark(exchange, year, {d: len(r) for d, r in chunk.items()})
        return total

    def append_day(self, exchange, day, fetch, skip_checked=False) -> int:
        """Ask the exchange for one day and store it. A download that fails raises and leaves no trace, so the day is
        asked again next time; only a clean 'no file' is remembered as a holiday."""
        if skip_checked and self.is_checked(exchange, day):
            return 0
        rows = PARSERS[exchange](fetch(URLS[exchange](day)), day)
        return self.append_days(exchange, {day: rows})

    # -- ISIN map
    def build_isin_map(self) -> Path:
        path = self.dir / "isin_map.parquet"
        parts = []
        for exchange, key in (("NSE", "symbol"), ("BSE", "code")):
            for f in self.price_files(exchange):
                parts.append(f"select exchange, {key} as key, symbol, isin, date from read_parquet('{_q(f)}') "
                             f"where isin is not null and {key} is not null")
        con = duckdb.connect()
        con.execute("create table m (exchange varchar, key varchar, symbol varchar, isin varchar, "
                    "first_seen date, last_seen date)")
        if parts:
            con.execute("insert into m select exchange, key, arg_max(symbol, date), isin, min(date), max(date) from ("
                        + " union all ".join(parts) + ") group by exchange, key, isin")
        self._write(con, "m", path, "exchange, key, first_seen")
        return path

    def fill_isins(self) -> int:
        """Give old rows an ISIN (and BSE rows a symbol) from the symbol or scrip-code map built from later files:
        the entry whose dates are nearest the row. A stock never seen with an ISIN stays unmapped, not guessed."""
        map_path = self.build_isin_map()
        filled = 0
        for exchange, key in (("NSE", "symbol"), ("BSE", "code")):
            for f in self.price_files(exchange):
                con = duckdb.connect()
                con.execute(f"create table t as select row_number() over () rn, {', '.join(NAMES)} from read_parquet('{_q(f)}')")
                missing = con.execute("select count(*) from t where isin is null or symbol is null").fetchone()[0]
                if not missing:
                    continue
                con.execute(f"""
                    create table fix as
                    select rn, isin, symbol from (
                        select t.rn, m.isin, m.symbol, row_number() over (partition by t.rn order by
                            case when t.date < m.first_seen then date_diff('day', t.date, m.first_seen)
                                 when t.date > m.last_seen then date_diff('day', m.last_seen, t.date) else 0 end,
                            m.last_seen desc) k
                        from t join read_parquet('{_q(map_path)}') m
                          on m.exchange = '{exchange}' and m.key = t.{key}
                        where t.isin is null or t.symbol is null) where k = 1""")
                n = con.execute("select count(*) from t join fix using (rn) where (t.isin is null and fix.isin is not null)"
                                " or (t.symbol is null and fix.symbol is not null)").fetchone()[0]
                if not n:
                    continue
                con.execute("update t set isin = coalesce(t.isin, fix.isin), symbol = coalesce(t.symbol, fix.symbol) "
                            "from fix where t.rn = fix.rn")
                con.execute(f"create table out as select {', '.join(NAMES)} from t")
                self._write(con, "out", f, ORDER)
                filled += n
        return filled

    # -- corporate actions
    def fetch_actions(self, start: date, end: date, fetch_json) -> int:
        """NSE's corporate-actions API, one calendar year per call, parsed by rules and stored once."""
        events = []
        for year in range(start.year, end.year + 1):
            a, b = max(start, date(year, 1, 1)), min(end, date(year, 12, 31))
            path = (f"/api/corporates-corporateActions?index=equities&from_date={a:%d-%m-%Y}&to_date={b:%d-%m-%Y}")
            events += [e for e in (parse_action(i) for i in (fetch_json(path) or [])) if e["ex_date"]]
        target = self.dir / "corporate_actions.parquet"
        con = duckdb.connect()
        con.execute("create table e (symbol varchar, ex_date date, company varchar, subject varchar, kind varchar, "
                    "factor double, amount double, face_value double)")
        if target.exists():
            con.execute(f"insert into e select symbol, ex_date, company, subject, kind, factor, amount, face_value "
                        f"from read_parquet('{_q(target)}')")
        before = con.execute("select count(*) from e").fetchone()[0]
        known = set(con.execute("select symbol, ex_date, subject from e").fetchall())
        fresh = {}
        for e in events:
            k = (e["symbol"], e["ex_date"], e["subject"])
            if k not in known:
                fresh[k] = e
        if fresh:
            con.executemany("insert into e values (?, ?, ?, ?, ?, ?, ?, ?)",
                            [(e["symbol"], e["ex_date"], e["company"], e["subject"], e["kind"], e["factor"],
                              e["amount"], e["face_value"]) for e in fresh.values()])
        self._write(con, "e", target, "symbol, ex_date, subject")
        return con.execute("select count(*) from e").fetchone()[0] - before

    # -- Yahoo: gaps only
    def existing_dates(self, exchange, symbol) -> set[date]:
        files = self.price_files(exchange)
        if not files:
            return set()
        glob = _q(self.dir / f"prices-{exchange}-*.parquet")
        return {d for (d,) in duckdb.execute(
            f"select date from read_parquet('{glob}') where symbol = ? or code = ?", [symbol, symbol]).fetchall()}

    def gap_days(self, exchange) -> list[date]:
        """Weekdays the other exchange has stock rows for and this one asked about and got nothing."""
        other = "BSE" if exchange == "NSE" else "NSE"
        out = []
        for f in sorted(self.dir.glob(f"checked-{exchange}-*.parquet")):
            for (d,) in duckdb.execute(f"select date from read_parquet('{_q(f)}') where rows = 0").fetchall():
                if d.weekday() < 5 and (self.rows_for(other, d) or 0) > 0:
                    out.append(d)
        return sorted(out)

    def fill_gaps(self, exchange, symbol, start: date, end: date, fetch_json) -> int:
        """Add Yahoo daily bars for this stock on days the store has none, between explicit start and end dates."""
        have = self.existing_dates(exchange, symbol)
        chart = fetch_json(yahoo_url(symbol, exchange, start, end))
        result = ((chart or {}).get("chart") or {}).get("result") or []
        if not result or not result[0].get("timestamp"):
            return 0
        q = result[0]["indicators"]["quote"][0]
        isin = self._known_isin(exchange, symbol)
        fresh: dict[date, list[dict]] = {}
        for i, ts in enumerate(result[0]["timestamp"]):
            day = datetime.fromtimestamp(ts, timezone.utc).date()
            if day in have or not (start <= day <= end) or q["close"][i] is None:
                continue
            fresh.setdefault(day, []).append(_row(
                exchange, day, "yahoo", symbol=None if exchange == "BSE" else symbol,
                code=symbol if exchange == "BSE" else None, isin=isin, open=q["open"][i], high=q["high"][i],
                low=q["low"][i], close=q["close"][i], volume=q["volume"][i]))
        added = 0
        for year in sorted({d.year for d in fresh}):
            rows = [r for d, rs in fresh.items() if d.year == year for r in rs]
            con = self._open_year(exchange, year)
            self._insert(con, rows)
            self._write(con, "t", self._prices(exchange, year), ORDER)
            added += len(rows)
        return added

    def _known_isin(self, exchange, symbol):
        if not self.price_files(exchange):
            return None
        glob = _q(self.dir / f"prices-{exchange}-*.parquet")
        got = duckdb.execute(f"select isin from read_parquet('{glob}') where (symbol = ? or code = ?) and isin is not null "
                             "limit 1", [symbol, symbol]).fetchone()
        return got[0] if got else None

    # -- the report
    def report(self) -> dict:
        by_year: dict[str, dict[str, int]] = {}
        span: dict[str, dict] = {}
        for f in self.price_files():
            _, exchange, year = f.stem.split("-")
            n, lo, hi = duckdb.execute(f"select count(*), min(date), max(date) from read_parquet('{_q(f)}')").fetchone()
            by_year.setdefault(exchange, {})[year] = n
            s = span.setdefault(exchange, {"first": lo, "last": hi})
            s["first"], s["last"] = min(s["first"], lo), max(s["last"], hi)
        return {"by_year": {e: dict(sorted(y.items())) for e, y in sorted(by_year.items())},
                "by_exchange": {e: sum(y.values()) for e, y in sorted(by_year.items())},
                "span": {e: {"first": str(s["first"]), "last": str(s["last"])} for e, s in span.items()},
                "total": sum(sum(y.values()) for y in by_year.values())}

    def write_report(self) -> Path:
        path = self.dir / "report.json"
        path.write_text(json.dumps(self.report(), indent=1))
        return path


def report_markdown(rep: dict) -> str:
    lines = ["| Exchange | Year | Rows |", "|---|---|---:|"]
    for exchange, years in rep["by_year"].items():
        lines += [f"| {exchange} | {year} | {n} |" for year, n in years.items()]
    lines += [""] + [f"{e}: {n} rows, {rep['span'][e]['first']} to {rep['span'][e]['last']}"
                     for e, n in rep["by_exchange"].items()]
    lines.append(f"Total: {rep['total']}")
    return "\n".join(lines)


# ---- reading it back with DuckDB ----------------------------------------------------------------------------------

def open_history(location, fetch=None, cache=None, force_download=False) -> duckdb.DuckDBPyConnection:
    """A DuckDB connection with one view `prices` over every price file. `location` is a directory of files, or a list of
    release-asset URLs. URLs are read by HTTP range requests; if that fails (or `force_download`), each file is downloaded
    to `cache` and read from disk, which is the fallback the probe (T2) names."""
    con = duckdb.connect()
    if isinstance(location, (str, Path)) and not str(location).startswith("http"):
        con.execute(f"create view prices as select * from read_parquet('{_q(Path(location) / 'prices-*.parquet')}', "
                    "union_by_name = true)")
        return con
    urls = [location] if isinstance(location, str) else list(location)
    if not force_download:
        try:
            con.execute("install httpfs; load httpfs")
            listing = ", ".join(f"'{_q(u)}'" for u in urls)
            con.execute(f"create view prices as select * from read_parquet([{listing}], union_by_name = true)")
            con.execute("select count(*) from prices").fetchone()
            return con
        except Exception:
            con = duckdb.connect()
    fetch = fetch or http_fetch
    cache = Path(cache or Path.cwd() / ".history-cache")
    cache.mkdir(parents=True, exist_ok=True)
    local = []
    for u in urls:
        blob = fetch(u)
        if not blob:
            raise FileNotFoundError(u)
        target = cache / u.rsplit("/", 1)[-1]
        target.write_bytes(blob)
        local.append(target)
    listing = ", ".join(f"'{_q(p)}'" for p in local)
    con.execute(f"create view prices as select * from read_parquet([{listing}], union_by_name = true)")
    return con


# ---- corporate actions ----------------------------------------------------------------------------------------------

_MONEY = re.compile(r"\bR[se]s?\b\.?\s*(\d+(?:\.\d+)?)", re.I)


def parse_action(item: dict) -> dict:
    """One NSE corporate-action row. The subject is free text, so it is read by rules: split (old face value over new),
    bonus a:b (a new shares for b held, factor (a+b)/b), dividend (amount in rupees); anything else is kept as 'other'."""
    subject = (item.get("subject") or "").strip()
    low = subject.lower()
    kind, factor, amount = "other", None, None
    money = [float(x) for x in _MONEY.findall(subject)]
    bonus = re.search(r"bonus\D*(\d+)\s*:\s*(\d+)", low)
    if bonus:
        a, b = int(bonus.group(1)), int(bonus.group(2))
        kind, factor = "bonus", ((a + b) / b if b else None)
    elif "split" in low or "sub-division" in low or "subdivision" in low:
        kind = "split"
        if len(money) >= 2 and money[1] > 0:
            factor = money[0] / money[1]
    elif "dividend" in low:
        kind = "dividend"
        amount = money[0] if money else None
    elif "rights" in low:
        kind = "rights"
    try:
        ex = datetime.strptime((item.get("exDate") or "").strip(), "%d-%b-%Y").date()
    except ValueError:
        ex = None
    return {"symbol": (item.get("symbol") or "").strip(), "ex_date": ex, "company": (item.get("comp") or "").strip(),
            "subject": subject, "kind": kind, "factor": factor, "amount": amount, "face_value": _num(item.get("faceVal"))}


# ---- Yahoo, for gaps only ---------------------------------------------------------------------------------------------

def yahoo_url(symbol: str, exchange: str, start: date, end: date) -> str:
    """Explicit start and end always: `range=max` silently returns monthly bars."""
    p1 = int(datetime(start.year, start.month, start.day, tzinfo=timezone.utc).timestamp())
    stop = end + timedelta(days=1)
    p2 = int(datetime(stop.year, stop.month, stop.day, tzinfo=timezone.utc).timestamp())
    suffix = "NS" if exchange == "NSE" else "BO"
    return (f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}.{suffix}"
            f"?period1={p1}&period2={p2}&interval=1d&events=div,splits")


# ---- the drivers ------------------------------------------------------------------------------------------------------

def weekdays(start: date, end: date):
    day = start
    while day <= end:
        if day.weekday() < 5:
            yield day
        day += timedelta(days=1)


def backfill(store: HistoryStore, exchange: str, start: date, end: date, fetch, flush_every=30, pause=0.0) -> dict:
    """Walk the weekdays from start to end, fetch each day not yet asked, and write in batches so a crash loses at most
    one batch and a rerun carries on where it stopped. (Saturday special sessions are not walked.)"""
    asked = with_data = rows_total = 0
    batch: dict[date, list[dict]] = {}

    def flush():
        nonlocal rows_total
        if batch:
            rows_total += store.append_days(exchange, dict(batch))
            batch.clear()

    try:
        for day in weekdays(start, end):
            if store.is_checked(exchange, day):
                continue
            rows = PARSERS[exchange](fetch(URLS[exchange](day)), day)
            asked += 1
            with_data += bool(rows)
            batch[day] = rows
            if len(batch) >= flush_every:
                flush()
            if pause:
                time.sleep(pause)
    finally:
        flush()
    return {"days_asked": asked, "days_with_data": with_data, "rows": rows_total}


def daily(store: HistoryStore, today: date, fetch, exchanges=EXCHANGES, lookback=5, fetch_json=None) -> dict:
    """Append the newest day and re-ask the last few days that had no data yet (NSE publishes UDiFF after about 19:00 IST,
    BSE can lag). A day already stored is never fetched again, so running this twice is harmless."""
    out = {}
    for exchange in exchanges:
        asked = rows = 0
        for day in weekdays(today - timedelta(days=lookback - 1), today):
            if store.rows_for(exchange, day):
                continue
            rows += store.append_day(exchange, day, fetch)
            asked += 1
        out[exchange] = {"days_asked": asked, "rows": rows}
    if fetch_json:
        out["actions"] = store.fetch_actions(today - timedelta(days=lookback), today + timedelta(days=30), fetch_json)
    return out


# ---- command line (what the public workflows run) ------------------------------------------------------------------------

def _date(text: str) -> date:
    return datetime.strptime(text, "%Y-%m-%d").date()


def _json_fetch(base=""):
    def get(path_or_url):
        blob = http_fetch(path_or_url if path_or_url.startswith("http") else base + path_or_url)
        return json.loads(blob) if blob else None
    return get


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="python -m stockpilot.sources.history")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("backfill", "daily", "actions", "consolidate", "fill-gaps"):
        p = sub.add_parser(name)
        p.add_argument("--dir", default="out/history")
        if name in ("backfill", "actions"):
            p.add_argument("--from", dest="start", type=_date)
            p.add_argument("--to", dest="end", type=_date)
        if name in ("backfill", "daily", "fill-gaps"):
            p.add_argument("--exchange", choices=EXCHANGES)
        if name == "daily":
            p.add_argument("--actions", action="store_true", help="also fetch the next 30 days of corporate actions")
        if name == "backfill":
            p.add_argument("--pause", type=float, default=0.3)
        if name == "fill-gaps":
            p.add_argument("--limit", type=int, default=200)
    args = ap.parse_args(argv)
    store = HistoryStore(args.dir)
    today = datetime.now(IST).date()
    if args.cmd == "backfill":
        first = NSE_FIRST_DAY if args.exchange == "NSE" else BSE_FIRST_DAY
        print(json.dumps(backfill(store, args.exchange, args.start or first, args.end or today, http_fetch, pause=args.pause)))
    elif args.cmd == "daily":
        fetch_json = None
        if args.actions:
            from stockpilot.sources.nse_api import Session
            fetch_json = Session().fetch_json
        print(json.dumps(daily(store, today, http_fetch, exchanges=(args.exchange,) if args.exchange else EXCHANGES,
                               fetch_json=fetch_json), default=str))
    elif args.cmd == "actions":
        from stockpilot.sources.nse_api import Session
        print(store.fetch_actions(args.start or date(1995, 1, 1), args.end or today, Session().fetch_json))
    elif args.cmd == "consolidate":
        print(f"isin filled: {store.fill_isins()}")
        store.write_report()
        print(report_markdown(store.report()))
    elif args.cmd == "fill-gaps":
        get = _json_fetch()
        days = store.gap_days(args.exchange)
        print(f"{len(days)} gap days on {args.exchange}")
        if days:
            glob = _q(store.dir / f"prices-{args.exchange}-*.parquet")
            col = "symbol" if args.exchange == "NSE" else "code"
            keys = [k for (k,) in duckdb.execute(
                f"select {col} from read_parquet('{glob}') where date = (select max(date) from read_parquet('{glob}') "
                f"where date < ?) order by value desc nulls last limit ?", [days[0], args.limit]).fetchall() if k]
            added = 0
            for key in keys:
                added += store.fill_gaps(args.exchange, key, days[0], days[-1], get)
                time.sleep(4)                                 # Yahoo answers bursts with 429
            print(f"yahoo rows added: {added}")


if __name__ == "__main__":
    main()
