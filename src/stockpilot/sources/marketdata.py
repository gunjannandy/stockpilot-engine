"""Market data ingest. Each ingest takes a `fetch(url) -> bytes | None` (None means not published,
e.g. a holiday), so tests serve saved real files and production serves HTTP."""
import io
import tempfile
import zipfile
from datetime import date

import duckdb

NSE_ARCHIVES = "https://nsearchives.nseindia.com"
# Main board (EQ, BE, BZ) and SME (SM, ST); gold bonds, G-secs and other series are not stocks.
STOCK_SERIES = {"EQ", "BE", "BZ", "SM", "ST"}


NEW_FORMAT_FROM = date(2024, 1, 1)
NEW_FORMAT_SQL = """TradDt, TckrSymb, 'NSE', SctySrs, OpnPric, HghPric, LwPric, ClsPric, PrvsClsgPric,
                    TtlTradgVol, TtlTrfVal, TtlNbOfTxsExctd"""
LEGACY_SQL = """?::date, SYMBOL, 'NSE', SERIES, OPEN, HIGH, LOW, CLOSE, PREVCLOSE,
                TOTTRDQTY, TOTTRDVAL, TOTALTRADES"""


def nse_bhavcopy_url(day: date) -> str:
    if day >= NEW_FORMAT_FROM:
        return f"{NSE_ARCHIVES}/content/cm/BhavCopy_NSE_CM_0_0_0_{day:%Y%m%d}_F_0000.csv.zip"
    mon = day.strftime("%b").upper()
    return f"{NSE_ARCHIVES}/content/historical/EQUITIES/{day.year}/{mon}/cm{day:%d}{mon}{day.year}bhav.csv.zip"


def ingest_nse_bhavcopy(db: duckdb.DuckDBPyConnection, day: date, fetch) -> int:
    """Load one day's NSE cash-market bhavcopy into `prices`. Returns the rows stored."""
    blob = fetch(nse_bhavcopy_url(day))
    if not blob:
        return 0
    series = ", ".join(f"'{s}'" for s in sorted(STOCK_SERIES))
    with zipfile.ZipFile(io.BytesIO(blob)) as zf, tempfile.TemporaryDirectory() as tmp:
        csv_path = zf.extract(zf.namelist()[0], tmp)
        db.execute("delete from prices where date = ? and exchange = 'NSE'", [day])
        new = day >= NEW_FORMAT_FROM
        cols, series_col = (NEW_FORMAT_SQL, "SctySrs") if new else (LEGACY_SQL, "SERIES")
        params = [csv_path] if new else [day, csv_path]
        db.execute(f"""
            insert into prices
            select {cols}
            from read_csv(?, header = true, delim = ',', quote = '"', null_padding = true)
            where {series_col} in ({series})""", params)
    return db.execute("select count(*) from prices where date = ? and exchange = 'NSE'", [day]).fetchone()[0]


BSE_URL = "https://www.bseindia.com/download/BhavCopy/Equity/BhavCopy_BSE_CM_0_0_0_{day:%Y%m%d}_F_0000.CSV"
# BSE equity groups, main board and SME; F (debt), G (government), E and IF are not stocks.
BSE_STOCK_GROUPS = {"A", "B", "T", "X", "XT", "Z", "ZP", "M", "MT", "MS", "P", "R", "TS"}


class NotPublished(RuntimeError):
    """The exchange has not published the day's file yet (its site answers with a web page, not the file)."""


def ingest_bse_bhavcopy(db: duckdb.DuckDBPyConnection, day: date, fetch) -> int:
    """Load one day's BSE equity bhavcopy into `prices` with exchange 'BSE'. Before BSE publishes, its site answers
    with an HTML page where the file should be: that raises NotPublished, never a CSV parse error."""
    blob = fetch(BSE_URL.format(day=day))
    if not blob:
        return 0
    if b"FinInstrmTp" not in blob[:2000]:
        raise NotPublished(f"BSE has not published {day} yet")
    groups = ", ".join(f"'{g}'" for g in sorted(BSE_STOCK_GROUPS))
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/bse.csv"
        with open(path, "wb") as f:
            f.write(blob)
        db.execute("delete from prices where date = ? and exchange = 'BSE'", [day])
        db.execute(f"""
            insert into prices
            select {NEW_FORMAT_SQL.replace("'NSE'", "'BSE'")}
            from read_csv(?, header = true, delim = ',', quote = '"', null_padding = true)
            where FinInstrmTp = 'STK' and SctySrs in ({groups})""", [path])
    return db.execute("select count(*) from prices where date = ? and exchange = 'BSE'", [day]).fetchone()[0]


SPECIAL_LOG = "special_session"


def ingest_special_sessions(db: duckdb.DuckDBPyConnection, first: date, today: date, fetch) -> int:
    """Sessions on days the calendar calls closed (Budget Sunday, Muhurat evening, a swapped Saturday). The weekday
    rule and the holiday list cannot know them; the day's file exists only if NSE traded. Each closed day from
    `first` to `today` is asked about once (today is asked again until it is over, the file may not be out) and
    kept if it exists (NSE only: BSE history is not kept, and a lone BSE day would read as a jump against a months-old row). A missing session leaves the next trading day's `prev_close` out of line with the stored
    close, which reads as a price jump. Returns the days found."""
    from stockpilot.sources import exchange
    found = 0
    day = first
    while day <= today:
        done = db.execute("select 1 from fetch_log where source = ? and period = ?", [SPECIAL_LOG, day.isoformat()]).fetchone()
        if (not exchange.is_trading_day(db, day) and not done and not
                db.execute("select 1 from prices where date = ? limit 1", [day]).fetchone()):
            stored = ingest_nse_bhavcopy(db, day, fetch)
            found += bool(stored)
            if day < today:
                db.execute("insert or replace into fetch_log values (?, ?)", [SPECIAL_LOG, day.isoformat()])
        day = date.fromordinal(day.toordinal() + 1)
    return found


INDEX_URL = NSE_ARCHIVES + "/content/indices/ind_close_all_{day:%d%m%Y}.csv"


def ingest_index_closes(db: duckdb.DuckDBPyConnection, day: date, fetch) -> int:
    """Every NSE index's close with its P/E, P/B and dividend yield, for one day."""
    blob = fetch(INDEX_URL.format(day=day))
    if not blob:
        return 0
    with tempfile.TemporaryDirectory() as tmp:
        path = f"{tmp}/idx.csv"
        with open(path, "wb") as f:
            f.write(blob)
        db.execute("delete from index_levels where date = ?", [day])
        db.execute("""
            insert or replace into index_levels
            select distinct ?::date, "Index Name", try_cast("Closing Index Value" as double),
                   try_cast("P/E" as double), try_cast("P/B" as double), try_cast("Div Yield" as double)
            from read_csv(?, header = true, delim = ',', quote = '"', all_varchar = true)""", [day, path])
    return db.execute("select count(*) from index_levels where date = ?", [day]).fetchone()[0]
