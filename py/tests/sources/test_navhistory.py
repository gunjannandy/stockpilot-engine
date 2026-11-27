"""R17: NAV history backfill (AMFI report, mfapi fallback), resumable, and what the fund review and base rates do with it.
Fixtures only: no network."""
import json
import resource
import time
from datetime import date, timedelta

import pytest

from stockpilot import backup, fundcall, readiness, store

from stockpilot.analysis import fundreview
from stockpilot.sources import navhistory as nh

TODAY = date(2026, 11, 23)
CAT = "Equity Scheme - Flexi Cap Fund"
HEAD = "Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Date"


@pytest.fixture
def db(tmp_path):
    d = store.open(tmp_path / "t.duckdb", job="test")
    yield d
    store.close(d)


def isin(code):
    return f"INF{code:03d}"


def fund(db, code, plan="Direct Plan", option="Growth", category=CAT):
    db.execute("insert into funds values (?, ?, null, ?, ?, ?, ?, 'House')", [code, isin(code), f"Fund {code}", plan, option, category])


def hold(db, code):
    db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, source) values "
               "('mf', ?, ?, '2022-01-01', 10, 100, 'test')", [isin(code), isin(code)])


def nav_of(code, day, g=0.0005):
    return 100 * (1 + g * (1 + code % 7)) ** ((day - date(2020, 1, 1)).days)


def amfi_text(codes, start, end, other=(999,)):
    """What AMFI's report looks like for a window: category and AMC header lines, then rows (weekdays only)."""
    lines = [HEAD, "", f"Open Ended Schemes({CAT})", "", "Some Mutual Fund"]
    day = start
    while day <= end:
        if day.weekday() < 5:
            for c in [*codes, *other]:
                lines.append(f"{c};Fund {c};Direct Plan;GROWTH;{isin(c)};;{nav_of(c, day):.4f};{day.strftime('%d-%b-%Y')}")
        day += timedelta(days=1)
    return lines


def fake_open(codes, max_days=None, calls=None):
    def open_lines(url):
        q = dict(p.split("=") for p in url.split("?")[1].split("&"))
        start, end = (nh.parse_day(q["frmdt"]), nh.parse_day(q["todt"]))
        if calls is not None:
            calls.append((start, end))
        if max_days and (end - start).days + 1 > max_days:
            return iter(["Date range is too large"])
        return iter(amfi_text(codes, start, end))
    return open_lines


def seed_scope(db):
    for c in (1, 2, 3, 4, 5):
        fund(db, c)
    fund(db, 6, plan="Regular Plan")
    fund(db, 7, option="IDCW")
    fund(db, 8, category="Debt Scheme - Liquid Fund")
    hold(db, 1)
    hold(db, 6)


def test_scope_is_held_funds_plus_direct_growth_in_their_categories(db):
    seed_scope(db)
    assert nh.scope(db) == [1, 2, 3, 4, 5, 6]          # not the IDCW plan, not the debt fund, not a stock


def test_backfill_streams_filters_to_scope_and_is_idempotent(db):
    seed_scope(db)
    codes = nh.scope(db)
    start = TODAY - timedelta(days=100)
    run = lambda: nh.backfill(db, fake_open(codes), None, TODAY, start=start, window_days=40, sleep=lambda s: None)  # noqa: E731
    first = run()
    n = db.execute("select count(*) from navs").fetchone()[0]
    assert n == len(codes) * sum(1 for i in range((TODAY - start).days + 1) if (start + timedelta(days=i)).weekday() < 5)
    assert db.execute("select count(*) from navs where scheme_code = 999").fetchone()[0] == 0
    assert first["windows"] == 3 and first["rows"] == n
    again = run()
    assert again["windows"] == 0 and again["skipped"] == 3        # all recorded in fetch_log
    assert db.execute("select count(*) from navs").fetchone()[0] == n


def test_a_restart_resumes_after_the_last_finished_window(db):
    seed_scope(db)
    codes = nh.scope(db)
    start = TODAY - timedelta(days=100)
    seen = []

    def open_lines(url):
        if len(seen) == 2:
            raise KeyboardInterrupt            # the process dies during the third window
        seen.append(url)
        return fake_open(codes)(url)

    with pytest.raises(KeyboardInterrupt):
        nh.backfill(db, open_lines, None, TODAY, start=start, window_days=40, sleep=lambda s: None)
    calls = []
    nh.backfill(db, fake_open(codes, calls=calls), None, TODAY, start=start, window_days=40, sleep=lambda s: None)
    assert len(calls) == 1 and calls[0][1] == TODAY       # only the newest window was left


def test_a_new_day_fetches_only_the_new_days(db):
    seed_scope(db)
    codes = nh.scope(db)
    start = TODAY - timedelta(days=60)
    nh.backfill(db, fake_open(codes), None, TODAY, start=start, window_days=90, sleep=lambda s: None)
    calls = []
    nh.backfill(db, fake_open(codes, calls=calls), None, TODAY + timedelta(days=3), start=start + timedelta(days=3),
                window_days=90, sleep=lambda s: None)
    assert calls == [(TODAY + timedelta(days=1), TODAY + timedelta(days=3))]


def test_window_shrinks_when_amfi_refuses_a_big_range(db):
    seed_scope(db)
    codes = nh.scope(db)
    calls = []
    start = TODAY - timedelta(days=89)
    out = nh.backfill(db, fake_open(codes, max_days=30, calls=calls), None, TODAY, start=start, window_days=90,
                      sleep=lambda s: None)
    done = [tuple(date.fromisoformat(x) for x in p.split("/")) for (p,) in db.execute(
        "select period from fetch_log where source like 'navhistory:amfi:%'").fetchall()]
    assert out["failed"] == 0 and out["shrunk"] >= 1 and max((e - s).days + 1 for s, e in done) <= 30
    assert out["size"] <= 30 and len(calls) <= 8                     # after the first refusals it stays at the size that worked
    assert db.execute("select count(distinct date) from navs").fetchone()[0] >= 60


def test_amfi_failure_falls_back_to_mfapi_per_scheme_code(db):
    seed_scope(db)
    codes = nh.scope(db)

    def dead(url):
        raise OSError("blocked")

    def mfapi(url):
        code = int(url.rsplit("/", 1)[1])
        return {"meta": {}, "data": [{"date": (TODAY - timedelta(days=i)).strftime("%d-%m-%Y"), "nav": f"{100 + i}"}
                                     for i in range(0, 400)] + [{"date": "01-01-2001", "nav": "5"}]}

    out = nh.backfill(db, dead, mfapi, TODAY, start=TODAY - timedelta(days=365 * 5), window_days=90, sleep=lambda s: None)
    assert out["fallback"] == len(codes)
    assert db.execute("select count(*) from navs where date < '2021-01-01'").fetchone()[0] == 0     # older than 5 years dropped
    assert db.execute("select count(distinct scheme_code) from navs").fetchone()[0] == len(codes)
    again = nh.backfill(db, dead, mfapi, TODAY, start=TODAY - timedelta(days=365 * 5), window_days=90, sleep=lambda s: None)
    assert again["fallback"] == 0                          # each code is recorded once done


def test_changed_scope_refetches_but_does_not_duplicate(db):
    seed_scope(db)
    start = TODAY - timedelta(days=30)
    nh.backfill(db, fake_open(nh.scope(db)), None, TODAY, start=start, window_days=90, sleep=lambda s: None)
    fund(db, 9)
    hold(db, 9)
    calls = []
    nh.backfill(db, fake_open(nh.scope(db), calls=calls), None, TODAY, start=start, window_days=90, sleep=lambda s: None)
    assert calls                                           # a new held fund needs its history
    assert db.execute("select count(*) from navs where scheme_code = 9").fetchone()[0] > 0


def test_rows_parsing_skips_headers_and_bad_rows():
    lines = [HEAD, "Open Ended Schemes(X)", "AMC", "1;A;Direct Plan;GROWTH;INF1;;N.A.;01-Nov-2026", "2;B;Direct Plan;GROWTH;INF2;;12.5;03-Nov-2026",
             "bad;row", "3;C;Direct Plan;GROWTH;INF3;;x;03-Nov-2026"]
    assert list(nh.parse_amfi(lines)) == [(date(2026, 11, 3), 2, 12.5)]


def test_parses_a_line_copied_from_the_real_amfi_report():
    # Fetched from portal.amfiindia.com on 2026-11-23: code;name;plan;option;ISIN;ISIN;NAV;date
    real = ["Scheme Code;NAV Name;Plan;Option;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Net Asset Value;Date",
            "148921;Aditya Birla Sun Life Multi-Cap Fund-Direct Growth;Direct Plan;GROWTH;INF209KB1Y49;;23.39;16-Nov-2026"]
    assert list(nh.parse_amfi(real)) == [(date(2026, 11, 16), 148921, 23.39)]


def test_probe_reports_the_window_amfi_accepts(db):
    out = nh.probe(fake_open([1], max_days=180), TODAY, sizes=(30, 90, 180, 365), sleep=lambda s: None)
    assert out == {30: True, 90: True, 180: True, 365: False}


# ---- what the fund review and the base rates do with the history -------------------------------------

def month_days(years):
    """Month-end-ish business days over `years` back from TODAY, one NAV a month on the 20th plus TODAY."""
    out, d = [], TODAY
    for k in range(years * 12, 0, -1):
        y, m = divmod(TODAY.year * 12 + TODAY.month - 1 - k, 12)
        out.append(date(y, m + 1, 20))
    return out + [TODAY]


def seed_history(db, years):
    db.execute("delete from navs")
    for c in range(1, 17):
        if not db.execute("select 1 from funds where scheme_code = ?", [c]).fetchone():
            fund(db, c)
        for d in month_days(years):
            db.execute("insert or replace into navs values (?, ?, ?)", [d, c, 100 * (1 + 0.004 + 0.0006 * c) ** ((d - date(2018, 1, 1)).days / 30.44)])
    if not db.execute("select 1 from lots").fetchone():
        hold(db, 3)


def test_review_and_base_rates_change_with_history_length(db):
    seed_history(db, 1)
    short = fundreview.review(db, TODAY)[0]
    assert short["verdict"] == "Too early to judge" and short["rank"] is None
    assert fundcall.base_rates(db, TODAY) == {}
    db.execute("delete from navs")
    seed_history(db, 3)
    three = fundreview.review(db, TODAY)[0]
    assert three["rank"] == (14, 16) and three["verdict"] == "Review"          # code 3 grows slowest of the held pair... ranked, not refused
    assert fundcall.base_rates(db, TODAY) == {}                                 # 3 years: ranked now, but no 12-month outcome yet
    db.execute("delete from navs")
    seed_history(db, 6)
    six = fundreview.review(db, TODAY)[0]
    assert six["rank"] == three["rank"]
    rates = fundcall.base_rates(db, TODAY)
    assert rates and sum(r["n"] for r in rates.values()) > 0
    assert all(1 <= q <= 4 for _, q in rates)
    assert fundcall.rate_for(db, CAT, six["rank"])[0] is None                   # nothing stored yet: refused, not invented
    fundcall.save_base_rates(db, rates, TODAY)
    rate, why = fundcall.rate_for(db, CAT, six["rank"])
    assert rate and rate["periods"] >= fundcall.MIN_PERIODS and rate["n"] >= fundcall.MIN_N and why == ""


def test_health_gap_when_a_held_fund_has_under_three_years(db):
    seed_history(db, 1)
    gaps = nh.gaps(db, TODAY)
    assert len(gaps) == 1 and gaps[0].startswith("Fund NAV history reaches back only ")
    assert str(min(month_days(1))) in gaps[0]
    db.execute("delete from navs")
    seed_history(db, 4)
    assert nh.gaps(db, TODAY) == []




def test_no_new_table_and_no_order_code():
    import inspect
    src = inspect.getsource(nh)
    assert "place_order" not in src and "kite" not in src.lower()
    assert "fetch_log" in backup.MARKET_TABLES and "navs" in backup.MARKET_TABLES


def test_memory_and_time_on_a_big_fixture(db, capsys):
    """~600k rows streamed (all-scheme windows over 5 years' worth of lines), 6 in scope: memory stays flat."""
    for c in range(1, 7):
        fund(db, c)
    hold(db, 1)
    start = TODAY - timedelta(days=89)

    def big(url):
        q = dict(p.split("=") for p in url.split("?")[1].split("&"))
        s, e = nh.parse_day(q["frmdt"]), nh.parse_day(q["todt"])
        def gen():
            d = s
            while d <= e:
                if d.weekday() < 5:
                    for c in range(1, 14000):
                        yield f"{c};F;Direct Plan;GROWTH;I;;{100 + c % 50};{d.strftime('%d-%b-%Y')}"
                d += timedelta(days=1)
        return gen()

    before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    t = time.time()
    out = nh.backfill(db, big, None, TODAY, start=start, window_days=90, sleep=lambda s: None)
    secs, grown = time.time() - t, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - before
    print(f"R17 measure: {out['seen']} lines streamed, {out['rows']} stored, {secs:.1f}s, peak RSS growth {grown / 1024:.1f} MB")
    assert out["rows"] == 6 * 64 and out["seen"] > 800_000
    assert grown < 150 * 1024                              # KB: far under the VM's 1 GB


def test_the_nightly_job_keeps_appending_the_days_navs(db):
    """`sp nav` stores every scheme's NAV under (date, scheme): a second night adds rows, it does not replace the history."""
    from stockpilot.sources import funds
    def navall(day, nav):
        return (f"Scheme Code;ISIN Div Payout/Growth;ISIN Div Reinvestment;Scheme Name;Plan;Option;NAV;Date\n\n"
                f"Open Ended Schemes(Equity Scheme - Flexi Cap Fund)\nHouse\n1;INF001;-;Fund 1;Direct Plan;Growth;{nav};{day}\n").encode()
    funds.ingest_navall(db, lambda url: navall("20-Nov-2026", 100))
    funds.ingest_navall(db, lambda url: navall("23-Nov-2026", 101))
    assert db.execute("select count(*) from navs where scheme_code = 1").fetchone()[0] == 2
