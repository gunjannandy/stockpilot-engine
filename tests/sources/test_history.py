"""All-time price history (T5): parse the exchanges' daily files, keep them as Parquet by exchange and year,
append a day idempotently, report row counts, and let DuckDB read the lot. Fixtures only; no network."""
import io
import json
import zipfile
from datetime import date
from pathlib import Path

import duckdb
import pytest

from stockpilot.sources import history

FIXTURES = Path(__file__).parents[1] / "fixtures"
HTML_STUB = b"<html><body>File not found</body></html>" + b" " * 16000


def zipped(name: str, text: str) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr(name, text)
    return buf.getvalue()


BSE_LEGACY = (
    "SC_CODE,SC_NAME,SC_GROUP,SC_TYPE,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,NO_TRADES,NO_OF_SHRS,NET_TURNOV,TDCLOINDI\n"
    "500112,STATE BANK OF INDIA,A ,Q,100.5,102.0,99.0,101.25,101.0,100.0,1500,250000,25312500.00,\n"
    "590001,SOME DEBT,F ,F,10,10,10,10,10,10,1,1,10,\n")


def fixture_fetch(url: str) -> bytes | None:
    path = FIXTURES / url.rsplit("/", 1)[-1]
    return path.read_bytes() if path.exists() else None


# ---- parsing -----------------------------------------------------------------------------------------------

def test_parses_a_legacy_nse_file_keeping_sme_and_dropping_non_stocks():
    rows = history.parse_nse(fixture_fetch("cm29DEC2023bhav.csv.zip"), date(2023, 12, 29))
    by = {r["symbol"]: r for r in rows}
    assert by["RELIANCE"]["close"] == 2584.95 and by["RELIANCE"]["isin"] == "INE002A01018"
    assert by["RELIANCE"]["exchange"] == "NSE" and by["RELIANCE"]["date"] == date(2023, 12, 29)
    assert by["AATMAJ"]["series"] == "SM"                      # SME stays in
    assert by["RELIANCE"]["trades"] == 248419 and by["RELIANCE"]["volume"] == 5432292


def test_parses_a_udiff_nse_file():
    rows = history.parse_nse(fixture_fetch("BhavCopy_NSE_CM_0_0_0_20261120_F_0000.csv.zip"), date(2026, 11, 20))
    by = {r["symbol"]: r for r in rows}
    assert by["SBIN"]["close"] == 1165.10 and by["SBIN"]["isin"] == "INE062A01020"
    assert "SGBJUN28" not in by                                # gold bond series GB is not a stock
    assert by["MHHL"]["series"] in {"SM", "ST"}


def test_a_missing_nse_day_gives_no_rows():
    assert history.parse_nse(None, date(2026, 11, 22)) == []


def test_a_bse_html_stub_is_not_a_file_even_with_status_200():
    assert history.parse_bse(HTML_STUB, date(2010, 1, 1)) == []
    assert history.parse_bse(None, date(2010, 1, 1)) == []


def test_parses_a_legacy_bse_zip_keyed_on_scrip_code():
    rows = history.parse_bse(zipped("EQ050110.CSV", BSE_LEGACY), date(2010, 1, 5))
    assert len(rows) == 1                                      # the debt group F is dropped
    r = rows[0]
    assert (r["exchange"], r["code"], r["close"], r["trades"], r["volume"]) == ("BSE", "500112", 101.25, 1500, 250000)
    assert r["isin"] is None and r["symbol"] is None           # legacy BSE has neither; the map fills them


def test_parses_a_udiff_bse_csv_with_sme_groups():
    rows = history.parse_bse(fixture_fetch("BhavCopy_BSE_CM_0_0_0_20261120_F_0000.CSV"), date(2026, 11, 20))
    by = {r["symbol"]: r for r in rows}
    assert by["SBIN"]["code"] == "500112" and by["SBIN"]["isin"] == "INE062A01020"
    assert by["CNINFOTECH"]["series"] == "M"                   # BSE SME group


def test_urls_follow_each_exchanges_format_by_date():
    assert history.nse_url(date(1994, 11, 3)).endswith("/1994/NOV/cm03NOV1994bhav.csv.zip")
    assert history.nse_url(date(2024, 7, 5)).endswith("/2024/JUL/cm05JUL2024bhav.csv.zip")
    assert history.nse_url(date(2024, 7, 8)).endswith("BhavCopy_NSE_CM_0_0_0_20240708_F_0000.csv.zip")
    assert history.bse_url(date(2010, 1, 5)).endswith("/EQ050110_CSV.ZIP")
    assert history.bse_url(date(2024, 7, 8)).endswith("BhavCopy_BSE_CM_0_0_0_20240708_F_0000.CSV")


# ---- the store: Parquet by exchange and year ---------------------------------------------------------------

def nse_fetch(url):
    if "29DEC2023" in url:
        return fixture_fetch("cm29DEC2023bhav.csv.zip")
    if "20261120" in url:
        return fixture_fetch("BhavCopy_NSE_CM_0_0_0_20261120_F_0000.csv.zip")
    return None


def test_appending_a_day_writes_one_parquet_file_per_exchange_and_year(tmp_path):
    store = history.HistoryStore(tmp_path)
    n = store.append_day("NSE", date(2023, 12, 29), nse_fetch)
    assert n == 3
    assert [p.name for p in sorted(tmp_path.glob("prices-*.parquet"))] == ["prices-NSE-2023.parquet"]
    store.append_day("NSE", date(2026, 11, 20), nse_fetch)
    assert (tmp_path / "prices-NSE-2026.parquet").exists()


def test_appending_the_same_day_twice_changes_nothing(tmp_path):
    store = history.HistoryStore(tmp_path)
    store.append_day("NSE", date(2023, 12, 29), nse_fetch)
    first = duckdb.execute(f"select * from read_parquet('{tmp_path}/prices-NSE-2023.parquet') order by symbol").fetchall()
    store.append_day("NSE", date(2023, 12, 29), nse_fetch)
    again = duckdb.execute(f"select * from read_parquet('{tmp_path}/prices-NSE-2023.parquet') order by symbol").fetchall()
    assert first == again and len(again) == 3


def test_a_holiday_is_remembered_so_a_rerun_does_not_ask_again(tmp_path):
    store = history.HistoryStore(tmp_path)
    asked = []

    def fetch(url):
        asked.append(url)
        return None

    assert store.append_day("NSE", date(2023, 12, 30), fetch) == 0
    assert store.is_checked("NSE", date(2023, 12, 30))
    store.append_day("NSE", date(2023, 12, 30), fetch, skip_checked=True)
    assert len(asked) == 1


def test_a_failing_download_is_not_remembered_as_a_holiday(tmp_path):
    store = history.HistoryStore(tmp_path)

    def boom(url):
        raise OSError("network down")

    with pytest.raises(OSError):
        store.append_day("NSE", date(2023, 12, 29), boom)
    assert not store.is_checked("NSE", date(2023, 12, 29))


def test_files_are_sorted_by_isin_and_date_and_compressed_with_zstd(tmp_path):
    history.HistoryStore(tmp_path).append_day("NSE", date(2023, 12, 29), nse_fetch)
    path = tmp_path / "prices-NSE-2023.parquet"
    codec = duckdb.execute(f"select compression from parquet_metadata('{path}') limit 1").fetchone()[0]
    assert codec.upper() == "ZSTD"
    isins = [r[0] for r in duckdb.execute(f"select isin from read_parquet('{path}')").fetchall()]
    assert isins == sorted(isins)


# ---- symbol-to-ISIN map for old rows ------------------------------------------------------------------------

def test_old_rows_without_isin_get_one_from_the_symbol_map(tmp_path):
    store = history.HistoryStore(tmp_path)
    old = ("SYMBOL,SERIES,OPEN,HIGH,LOW,CLOSE,LAST,PREVCLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP\n"
           "RELIANCE,EQ,500,510,490,505,505,498,1000,505000,03-JAN-2000\n"
           "GONECO,EQ,10,11,9,10,10,10,5,50,03-JAN-2000\n")

    def fetch(url):
        if "03JAN2000" in url:
            return zipped("cm03JAN2000bhav.csv", old)
        return nse_fetch(url)

    store.append_day("NSE", date(2000, 1, 3), fetch)
    store.append_day("NSE", date(2023, 12, 29), fetch)
    store.fill_isins()
    rows = dict(duckdb.execute(
        f"select symbol, isin from read_parquet('{tmp_path}/prices-NSE-2000.parquet')").fetchall())
    assert rows["RELIANCE"] == "INE002A01018"        # carried backwards from the 2023 file
    assert rows["GONECO"] is None                    # a delisted symbol we never saw with an ISIN stays unmapped, not guessed


def test_bse_scrip_codes_get_symbol_and_isin_from_a_later_udiff_file(tmp_path):
    store = history.HistoryStore(tmp_path)

    def fetch(url):
        if "EQ050110" in url:
            return zipped("EQ050110.CSV", BSE_LEGACY)
        if "20261120" in url:
            return fixture_fetch("BhavCopy_BSE_CM_0_0_0_20261120_F_0000.CSV")
        return None

    store.append_day("BSE", date(2010, 1, 5), fetch)
    store.append_day("BSE", date(2026, 11, 20), fetch)
    store.fill_isins()
    row = duckdb.execute(f"select symbol, isin from read_parquet('{tmp_path}/prices-BSE-2010.parquet')").fetchone()
    assert row == ("SBIN", "INE062A01020")


# ---- the report and DuckDB ------------------------------------------------------------------------------------

def test_report_counts_rows_per_exchange_and_year(tmp_path):
    store = history.HistoryStore(tmp_path)
    store.append_day("NSE", date(2023, 12, 29), nse_fetch)
    store.append_day("NSE", date(2026, 11, 20), nse_fetch)
    rep = store.report()
    assert rep["by_year"]["NSE"] == {"2023": 3, "2026": 5}
    assert rep["total"] == 8
    md = history.report_markdown(rep)
    assert "| NSE | 2023 | 3 |" in md and "Total: 8" in md


def test_duckdb_reads_every_published_file_as_one_table(tmp_path):
    store = history.HistoryStore(tmp_path)
    store.append_day("NSE", date(2023, 12, 29), nse_fetch)
    store.append_day("NSE", date(2026, 11, 20), nse_fetch)
    con = history.open_history(tmp_path)
    assert con.execute("select count(*) from prices").fetchone()[0] == 8
    first = con.execute("select min(date) from prices where symbol = 'SBIN'").fetchone()[0]
    assert first == date(2023, 12, 29)


def test_open_history_falls_back_to_downloading_when_range_reads_fail(tmp_path):
    src = tmp_path / "src"
    history.HistoryStore(src).append_day("NSE", date(2023, 12, 29), nse_fetch)
    blob = (src / "prices-NSE-2023.parquet").read_bytes()
    urls = ["https://example.invalid/releases/download/history-prices/prices-NSE-2023.parquet"]
    con = history.open_history(urls, fetch=lambda u: blob, cache=tmp_path / "cache", force_download=True)
    assert con.execute("select count(*) from prices").fetchone()[0] == 3


# ---- corporate actions ------------------------------------------------------------------------------------------

@pytest.mark.parametrize("subject, kind, factor, amount", [
    ("Fv Split Rs.10 To Re.1", "split", 10.0, None),
    ("FACE VALUE SPLIT (SUB-DIVISION) - FROM RS 10/- PER SHARE TO RS 2/- PER SHARE", "split", 5.0, None),
    ("Bonus 1:1", "bonus", 2.0, None),
    ("Bonus 3:2", "bonus", 2.5, None),
    ("Dividend - Rs 5 Per Share", "dividend", None, 5.0),
    ("Annual General Meeting", "other", None, None),
])
def test_corporate_action_subjects_are_parsed_by_rules(subject, kind, factor, amount):
    ev = history.parse_action({"symbol": "X", "exDate": "01-Jun-2006", "comp": "X LTD", "subject": subject, "faceVal": "10"})
    assert ev["kind"] == kind and ev["ex_date"] == date(2006, 6, 1) and ev["subject"] == subject
    assert ev["factor"] == factor and ev["amount"] == amount


def test_corporate_actions_are_stored_once_whatever_the_reruns(tmp_path):
    store = history.HistoryStore(tmp_path)
    page = [{"symbol": "RELIANCE", "exDate": "01-Jun-2006", "comp": "RELIANCE INDUSTRIES LTD",
             "subject": "Bonus 1:1", "faceVal": "10"}]
    calls = []

    def fetch_json(path):
        calls.append(path)
        return page

    store.fetch_actions(date(2006, 1, 1), date(2006, 12, 31), fetch_json)
    store.fetch_actions(date(2006, 1, 1), date(2006, 12, 31), fetch_json)
    n = duckdb.execute(f"select count(*) from read_parquet('{tmp_path}/corporate_actions.parquet')").fetchone()[0]
    assert n == 1
    assert "from_date=01-01-2006" in calls[0] and "to_date=31-12-2006" in calls[0]


# ---- yfinance only fills gaps ------------------------------------------------------------------------------------

def test_yahoo_url_always_has_explicit_start_and_end_never_range_max():
    url = history.yahoo_url("RELIANCE", "NSE", date(2024, 7, 8), date(2024, 7, 10))
    assert "RELIANCE.NS" in url and "period1=" in url and "period2=" in url and "range=" not in url
    assert history.yahoo_url("500112", "BSE", date(2024, 7, 8), date(2024, 7, 10)).count(".BO") == 1


def test_gap_fill_adds_only_missing_days_and_marks_the_source(tmp_path):
    store = history.HistoryStore(tmp_path)
    store.append_day("NSE", date(2023, 12, 29), nse_fetch)
    chart = {"chart": {"result": [{
        "timestamp": [1703808000, 1704067200],            # 2023-12-29 and 2024-01-01 (UTC midnight)
        "indicators": {"quote": [{"open": [1, 2], "high": [1, 2], "low": [1, 2], "close": [1.5, 2.5], "volume": [10, 20]}]}}]}}
    added = store.fill_gaps("NSE", "RELIANCE", date(2023, 12, 29), date(2024, 1, 1), lambda url: chart)
    assert added == 1                                      # 29 Dec already came from NSE itself
    rows = duckdb.execute(f"select date, close, source from read_parquet('{tmp_path}/prices-NSE-2024.parquet') "
                      "where symbol = 'RELIANCE'").fetchall()
    assert rows == [(date(2024, 1, 1), 2.5, "yahoo")]


def test_gap_days_are_days_one_exchange_has_and_the_other_lacks(tmp_path):
    store = history.HistoryStore(tmp_path)
    store.append_day("NSE", date(2023, 12, 29), nse_fetch)
    store.append_day("BSE", date(2023, 12, 29), lambda u: None)         # BSE gave nothing on a day NSE traded
    assert store.gap_days("BSE") == [date(2023, 12, 29)]
    assert store.gap_days("NSE") == []


# ---- the backfill driver ------------------------------------------------------------------------------------------

def test_backfill_walks_weekdays_only_and_resumes_without_refetching(tmp_path):
    store = history.HistoryStore(tmp_path)
    asked = []

    def fetch(url):
        asked.append(url)
        return nse_fetch(url)

    summary = history.backfill(store, "NSE", date(2023, 12, 28), date(2024, 1, 1), fetch)
    # 28, 29 Dec, 1 Jan are weekdays; 30, 31 Dec are a weekend and never asked
    assert len(asked) == 3 and summary == {"days_asked": 3, "days_with_data": 1, "rows": 3}
    asked.clear()
    again = history.backfill(store, "NSE", date(2023, 12, 28), date(2024, 1, 1), fetch)
    assert asked == [] and again["days_asked"] == 0


def test_the_daily_job_catches_up_on_days_that_were_not_yet_published(tmp_path):
    store = history.HistoryStore(tmp_path)
    store.append_day("NSE", date(2023, 12, 29), nse_fetch)
    out = history.daily(store, date(2023, 12, 29), nse_fetch, exchanges=("NSE",), lookback=3)
    assert out["NSE"]["rows"] == 0                         # nothing new; 29 Dec already present
    n = duckdb.execute(f"select count(*) from read_parquet('{tmp_path}/prices-NSE-2023.parquet')").fetchone()[0]
    assert n == 3


def test_report_json_round_trips(tmp_path):
    store = history.HistoryStore(tmp_path)
    store.append_day("NSE", date(2023, 12, 29), nse_fetch)
    path = store.write_report()
    assert json.loads(path.read_text())["total"] == 3


# ---- the public workflows -----------------------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["history-backfill", "history-daily"])
def test_public_workflows_parse_use_no_secrets_and_never_touch_private_data(name):
    import yaml
    root = Path(__file__).parents[2]
    path = root / "ops" / "public" / "workflows" / f"{name}.yml"   # the private repo keeps the public copies here
    if not path.exists():
        path = root / ".github" / "workflows" / f"{name}.yml"   # in the public engine they are the live workflows
    text = path.read_text()
    assert yaml.safe_load(text)["jobs"]
    assert "secrets." not in text and "cloudflare" not in text.lower()   # no Cloudflare or any other token in the public repo
    assert "history-prices" in text and "vault" not in text.lower()
