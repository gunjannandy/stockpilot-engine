"""Lane R9: quarterly fundamentals history from NSE XBRL filings. Real samples, temp DBs, no network."""
import copy
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path

from stockpilot import backup, store
from stockpilot.sources import filings

X = Path(__file__).parents[1] / "fixtures" / "dossier" / "xbrl"
OLD_INDEX = json.loads((X / "index_rows_per_symbol.json").read_text())
NEW_INDEX = json.loads((X / "integrated_index_TATASTEEL.json").read_text())
TODAY = date(2026, 11, 23)


def sample(name) -> bytes:
    return (X / name).read_bytes()


def in_file(name, tag, ctx="OneD"):
    """The number the sample file itself states for a tag in a context."""
    m = re.search(r'<[\w-]+:%s contextRef="%s"[^>]*>([-\d.]+)<' % (tag, ctx), sample(name).decode())
    return float(m.group(1))


def test_tata_steel_old_namespace():
    q = filings.parse_xbrl(sample("TATASTEEL_2024-12-31.xml"))
    f = "TATASTEEL_2024-12-31.xml"
    assert q["period_end"] == date(2024, 12, 31)
    assert q["revenue"] == in_file(f, "RevenueFromOperations")
    assert q["net_profit"] == in_file(f, "ProfitLossForPeriod")
    assert q["eps"] == in_file(f, "BasicEarningsLossPerShareFromContinuingAndDiscontinuedOperations") == 0.26
    assert q["operating_profit"] is None            # not tagged


def test_infosys_old_namespace():
    f = "INFY_2024-12-31.xml"
    q = filings.parse_xbrl(sample(f))
    assert (q["revenue"], q["net_profit"], q["eps"]) == (
        in_file(f, "RevenueFromOperations"), in_file(f, "ProfitLossForPeriod"), 16.43)


def test_bank_uses_interest_earned_and_its_own_tags():
    f = "HDFCBANK_2024-12-31.xml"
    q = filings.parse_xbrl(sample(f))
    assert q["revenue"] == in_file(f, "InterestEarned")
    assert q["net_profit"] == in_file(f, "ProfitLossForThePeriod")
    assert q["eps"] == in_file(f, "BasicEarningsPerShareAfterExtraordinaryItems") == 23.11
    assert q["operating_profit"] == in_file(f, "OperatingProfitBeforeProvisionAndContingencies")


def test_integrated_filing_namespace():
    f = "TATASTEEL_30-SEP-2026_integrated.xml"
    q = filings.parse_xbrl(sample(f))
    assert q["period_end"] == date(2026, 9, 30)
    assert q["revenue"] == in_file(f, "RevenueFromOperations") == 654362400000
    assert q["net_profit"] == in_file(f, "ProfitLossForPeriod")
    assert q["eps"] == 2.94


def test_year_to_date_context_is_ignored():
    q = filings.parse_xbrl(sample("TATASTEEL_30-SEP-2026_integrated.xml"))
    assert q["revenue"] != 1262305300000 and q["eps"] != 4.8


def test_context_ids_are_not_trusted():
    """A filer who names the quarter context something else still gets the 3-month numbers."""
    text = sample("TATASTEEL_2024-12-31.xml").decode().replace('"OneD"', '"Q3"').replace('"FourD"', '"Nine"')
    q = filings.parse_xbrl(text.encode())
    assert q["revenue"] == 536483000000.0 and q["eps"] == 0.26


def test_unreadable_files_parse_to_none():
    assert filings.parse_xbrl(b"<html>nope</html>") is None
    assert filings.parse_xbrl(b"not xml") is None
    assert filings.parse_xbrl(b'<!DOCTYPE x [<!ENTITY a "b">]><x/>') is None


def seed_filing(db, symbol="TCS", end=date(2026, 9, 30), filed=datetime(2026, 10, 10, 17, 0), cons=True, net=100.0):
    db.execute("insert into quarterly values ('INE1', ?, ?, ?, ?, 1000, null, ?, 5.0, 'u')",
               [symbol, end, cons, filed, net])


def test_history_is_point_in_time(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    seed_filing(db, end=date(2026, 6, 30), filed=datetime(2026, 7, 10, 17, 0))
    seed_filing(db, end=date(2026, 9, 30), filed=datetime(2026, 10, 10, 17, 0))
    assert [r["period_end"] for r in filings.history(db, "TCS", date(2026, 10, 9))] == [date(2026, 6, 30)]
    assert [r["period_end"] for r in filings.history(db, "TCS", date(2026, 10, 10))] == [
        date(2026, 9, 30), date(2026, 6, 30)]                       # newest first; a date covers its whole day
    assert filings.history(db, "TCS", datetime(2026, 10, 10, 16, 0))[0]["period_end"] == date(2026, 6, 30)
    assert filings.history(db, "NOPE", TODAY) == []


def test_history_prefers_consolidated_and_last_restatement_known_then(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    seed_filing(db, cons=False, net=1.0)
    seed_filing(db, cons=True, net=2.0)
    seed_filing(db, cons=True, net=3.0, filed=datetime(2026, 12, 1, 9, 0))      # a revision
    assert [r["net_profit"] for r in filings.history(db, "TCS", date(2026, 11, 1))] == [2.0]
    assert [r["net_profit"] for r in filings.history(db, "TCS", date(2026, 12, 2))] == [3.0]


def test_history_returns_at_most_n(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    for i in range(10):
        seed_filing(db, end=date(2024 + i // 4, (i % 4) * 3 + 3, 28), filed=datetime(2025, 1, 1))
    assert len(filings.history(db, "TCS", TODAY)) == 8
    assert len(filings.history(db, "TCS", TODAY, n=3)) == 3


# ---- backfill -------------------------------------------------------------------------------------------------

OLD_PATH = "/api/corporates-financial-results?index=equities&symbol=%s&period=Quarterly"
NEW_PATH = ("/api/integrated-filing-results?index=equities&symbol=%s&period_ended=all"
            "&type=Integrated%%20Filing-%%20Financials")


def old_row(symbol, end, cons=True, url=None):
    r = copy.deepcopy(next(r for r in OLD_INDEX if r["symbol"] == "TATASTEEL" and r["consolidated"] == "Consolidated"))
    r.update(symbol=symbol, toDate=end.strftime("%d-%b-%Y"), consolidated="Consolidated" if cons else "Non-Consolidated",
             xbrl=url or f"https://files/{symbol}/{end}/{cons}.xml")
    return r


def new_row(end, cons=True, size="49.17 KB", url=None):
    r = copy.deepcopy(next(r for r in NEW_INDEX if r["consolidated"] == "Consolidated"))
    r.update(qe_Date=end.strftime("%d-%b-%Y").upper(), consolidated="Consolidated" if cons else "Standalone",
             xbrlFileSize=size, xbrl=url or f"https://files/new/{end}/{cons}.xml")
    return r


class Fake:
    def __init__(self, old=None, new=None, files=None):
        self.old, self.new, self.files = old or {}, new or {}, files or {}
        self.calls, self.fetched = [], []

    def json(self, path):
        self.calls.append(path)
        for symbol, rows in self.old.items():
            if path == OLD_PATH % symbol:
                return rows
        for symbol, rows in self.new.items():
            if path == NEW_PATH % symbol:
                return {"data": rows, "totalCount": len(rows)}
        return [] if "corporates-financial" in path else {"data": [], "totalCount": 0}

    def file(self, url, max_bytes):
        self.fetched.append(url)
        if url in self.files:
            return self.files[url]
        m = re.search(r"(\d{4}-\d\d-\d\d)", url)             # a quarter that ends on the date in the url
        if not m:
            return sample("TATASTEEL_2024-12-31.xml")
        end = date.fromisoformat(m.group(1))
        return (sample("TATASTEEL_2024-12-31.xml").decode().replace("2024-12-31", str(end))
                .replace("2024-10-01", str(end - timedelta(days=91)))).encode()


def quarters(n, start=date(2023, 12, 31)):
    out, y, m = [], start.year, start.month
    for _ in range(n):
        out.append(date(y, m, 30 if m in (6, 9) else 31))
        y, m = (y + 1, 3) if m == 12 else (y, m + 3)
    return out


def test_backfill_takes_newest_12_quarters_from_both_feeds(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    qs = quarters(16, date(2021, 3, 31))                     # 16 quarters: Mar 2021 .. Dec 2024
    new = [date(2025, 3, 31), date(2025, 6, 30)]
    fake = Fake(old={"TATASTEEL": [old_row("TATASTEEL", d) for d in qs]},
                new={"TATASTEEL": [new_row(d) for d in new]})
    out = filings.backfill(db, fake.json, fake.file, ["TATASTEEL"], TODAY)
    ends = [r[0] for r in db.execute("select period_end from quarterly order by period_end desc").fetchall()]
    assert len(ends) == 12 and ends[0] == date(2025, 6, 30) and ends[-1] == date(2022, 9, 30)
    assert out["stored"] == 12
    assert db.execute("select count(*) from fetch_log where source = 'filings:TATASTEEL'").fetchone()[0] == 1


def test_backfill_stores_parsed_numbers(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    fake = Fake(old={"TATASTEEL": [old_row("TATASTEEL", date(2024, 12, 31))]})
    filings.backfill(db, fake.json, fake.file, ["TATASTEEL"], TODAY)
    row = db.execute("select isin, symbol, period_end, consolidated, filed_at, revenue, net_profit, eps, source_url "
                     "from quarterly").fetchone()
    assert row == ("INE081A01012", "TATASTEEL", date(2024, 12, 31), True, datetime(2025, 1, 27, 19, 15),
                   536483000000.0, 2954900000.0, 0.26, "https://files/TATASTEEL/2024-12-31/True.xml")


def test_backfill_prefers_consolidated_and_skips_standalone_when_it_exists(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    d = date(2024, 12, 31)
    fake = Fake(old={"TATASTEEL": [old_row("TATASTEEL", d, cons=False), old_row("TATASTEEL", d, cons=True)]})
    filings.backfill(db, fake.json, fake.file, ["TATASTEEL"], TODAY)
    assert fake.fetched == ["https://files/TATASTEEL/2024-12-31/True.xml"]
    d2 = date(2024, 9, 30)
    fake = Fake(old={"X": [old_row("X", d2, cons=False)]})            # no consolidated: the standalone is used
    filings.backfill(db, fake.json, fake.file, ["X"], TODAY)
    assert db.execute("select consolidated from quarterly where symbol = 'X'").fetchone() == (False,)


def test_backfill_resumes_from_fetch_log(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    fake = Fake(old={s: [old_row(s, date(2024, 12, 31))] for s in ("AAA", "BBB")})
    filings.backfill(db, fake.json, fake.file, ["AAA"], TODAY)
    fake = Fake(old={s: [old_row(s, date(2024, 12, 31))] for s in ("AAA", "BBB")})
    out = filings.backfill(db, fake.json, fake.file, ["AAA", "BBB"], TODAY)
    assert OLD_PATH % "AAA" not in fake.calls and OLD_PATH % "BBB" in fake.calls
    assert out["skipped_done"] == 1 and out["stored"] == 1


def test_a_failed_download_leaves_the_company_open_and_keeps_what_was_stored(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    rows = [old_row("AAA", date(2024, 12, 31)), old_row("AAA", date(2024, 9, 30), url="https://files/bad.xml")]
    fake = Fake(old={"AAA": rows})
    real = fake.file

    def flaky(url, max_bytes):
        if url.endswith("bad.xml"):
            raise OSError("reset")
        return real(url, max_bytes)

    out = filings.backfill(db, fake.json, flaky, ["AAA"], TODAY)
    assert out["failed"] == 1 and db.execute("select count(*) from quarterly").fetchone()[0] == 1
    assert db.execute("select count(*) from fetch_log where source = 'filings:AAA'").fetchone()[0] == 0
    fake2 = Fake(old={"AAA": rows})
    filings.backfill(db, fake2.json, fake2.file, ["AAA"], TODAY)
    assert fake2.fetched == ["https://files/bad.xml"]                # the stored one is not fetched again
    assert db.execute("select count(*) from fetch_log where source = 'filings:AAA'").fetchone()[0] == 1


def test_a_file_over_2_mb_is_skipped(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    d = date(2026, 9, 30)
    fake = Fake(new={"TATASTEEL": [new_row(d, cons=False, size="4.50 MB")]})
    out = filings.backfill(db, fake.json, fake.file, ["TATASTEEL"], TODAY)
    assert fake.fetched == [] and out["too_big"] == 1 and out["stored"] == 0
    assert db.execute("select count(*) from fetch_log where source = 'filings:TATASTEEL'").fetchone()[0] == 1
    # an old-feed file has no size in the index: the fetcher returns None when the file is over the cap
    fake = Fake(old={"BIG": [old_row("BIG", date(2024, 12, 31))]})
    out = filings.backfill(db, fake.json, lambda url, cap: None, ["BIG"], TODAY)
    assert out["too_big"] == 1 and out["stored"] == 0 and fake.calls


def test_the_size_cap_is_2_mb():
    assert filings.MAX_BYTES == 2 * 1024 * 1024
    assert filings.size_bytes("120.97 KB") == 120.97 * 1024 and filings.size_bytes("1.37 MB") < filings.MAX_BYTES
    assert filings.size_bytes("4.50 MB") > filings.MAX_BYTES and filings.size_bytes("0 Bytes") == 0
    assert filings.size_bytes(None) is None


def test_integrated_row_stores_filing_time_and_standalone_flag(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    fake = Fake(new={"TATASTEEL": [new_row(date(2026, 9, 30), url="https://files/i.xml")]},
                files={"https://files/i.xml": sample("TATASTEEL_30-SEP-2026_integrated.xml")})
    filings.backfill(db, fake.json, fake.file, ["TATASTEEL"], TODAY)
    assert db.execute("select period_end, consolidated, filed_at, revenue, eps from quarterly").fetchone() == (
        date(2026, 9, 30), True, datetime(2026, 11, 7, 17, 33, 17), 654362400000.0, 2.94)


def test_refresh_fetches_only_companies_whose_results_date_has_passed(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    for s in ("DUE", "QUIET", "NEW"):
        db.execute("insert into fetch_log values (?, '2026-08-01')", ["filings:" + s])
    seed_filing(db, "DUE", date(2026, 6, 30), datetime(2026, 8, 5, 10, 0))
    seed_filing(db, "QUIET", date(2026, 6, 30), datetime(2026, 8, 5, 10, 0))
    db.execute("insert into results_calendar values ('DUE', '2026-11-05', 'Financial Results', '')")
    db.execute("insert into results_calendar values ('QUIET', '2026-12-10', 'Financial Results', '')")   # future
    fake = Fake(new={s: [new_row(date(2026, 9, 30))] for s in ("DUE", "QUIET")})
    out = filings.refresh(db, fake.json, fake.file, ["DUE", "QUIET", "NEW"], TODAY)
    assert fake.calls and all("symbol=DUE" in c for c in fake.calls)
    assert out["stored"] == 1 and out["companies"] == 1
    # the next week the filing is in, so the company is no longer due
    fake = Fake(new={"DUE": [new_row(date(2026, 9, 30))]})
    assert filings.refresh(db, fake.json, fake.file, ["DUE"], date(2026, 11, 30))["companies"] == 0


def test_file_fetcher_shares_the_session_spacing_and_stops_at_the_cap():
    import io
    import time

    class Resp(io.BytesIO):
        headers = {}

    class Opener:
        def __init__(self, body):
            self.body, self.urls = body, []

        def open(self, req, timeout):
            self.urls.append(req.full_url)
            return Resp(self.body)

    class S:
        _last = time.time()

        def __init__(self, body):
            self._opener = Opener(body)

        def fetch_json(self, path):
            return []

    s = S(b"<x/>")
    fj, ff = filings.fetchers(s)
    t = time.time()
    assert ff("https://nsearchives/x.xml", 100) == b"<x/>"
    assert time.time() - t >= 0.9                                   # waited out the 1.1 s spacing
    assert fj("/p") == []
    assert filings.fetchers(S(b"x" * 101))[1]("https://nsearchives/big.xml", 100) is None


def test_quarterly_table_is_backed_up():
    assert "quarterly" in backup.MARKET_TABLES


def test_symbols_to_load_puts_holdings_then_watchlist_first(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    db.execute("insert into holdings values ('2026-11-20 10:00:00', 'stock', 'ZED', 'I1', 1, 1, 'kite')")
    db.execute("insert into holdings values ('2026-11-01 10:00:00', 'stock', 'OLD', 'I2', 1, 1, 'kite')")
    db.execute("insert into watchlist (symbol, exchange, added_by) values ('WATCH', 'NSE', 'papa')")
    assert filings.symbols_to_load(db, TODAY) == ["ZED", "WATCH"]


