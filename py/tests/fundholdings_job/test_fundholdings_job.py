from datetime import date

from stockpilot.jobs import fundholdings as job


def got(fund_id, as_of, rows):
    return {"matched": [{"fund_id": fund_id, "name": "F", "amc": "H", "as_of": as_of, "rows": rows}],
            "unmatched": [], "failed": []}


def r(isin, pct):
    return {"isin": isin, "name": isin, "pct_nav": pct}


def test_latest_month_wins_and_holdings_are_isin_name_pct_triples():
    houses = {"A": got("f1", date(2026, 9, 30), [r("INE000A01010", 5.0)]),
              "B": got("f1", date(2026, 10, 31), [r("INE000B01012", 7.5), r("IN0000000012", None)])}
    rows = job.rows_from(houses)
    assert len(rows) == 1 and rows[0]["as_of"] == "2026-10-31"
    assert rows[0]["holdings_json"] == '[["INE000B01012","INE000B01012",7.5],["IN0000000012","IN0000000012",null]]'


def test_a_fund_without_holdings_is_left_out():
    assert job.rows_from({"A": got("f1", None, [])}) == []


def test_a_house_that_cannot_be_fetched_is_recorded_and_the_run_goes_on(monkeypatch):
    lines = []
    monkeypatch.setattr(job.fund_universe, "parse_navall", lambda b: [])
    monkeypatch.setattr(job.fund_universe, "group_funds", lambda s: [])
    monkeypatch.setattr(job.fh, "resolve_urls", lambda f, e: (_ for _ in ()).throw(OSError("403")))
    assert job.collect(lambda u: b"x", {}, progress=lines.append) == []
    assert len(lines) == len(job.fh.HOUSES) and all("cannot be fetched" in l for l in lines)
