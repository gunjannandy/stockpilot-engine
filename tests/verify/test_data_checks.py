"""Checks 1 to 6, each with a clean fixture that passes and a deliberately broken one that it catches."""
import json
import shutil
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from vhelpers import DAY, price_rows, read, write
from helpers import insert_prices
from stockpilot import store
from stockpilot.verify import Ctx, data, flags

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def site(site_built, tmp_path):
    """A private copy of the built site that a test may break."""
    db, out, day = site_built
    dest = tmp_path / "site"
    shutil.copytree(out, dest)
    return db, dest, day


def ctx_for(db, day, site=None, **kw):
    return Ctx(db=db, day=day, site=site, root=ROOT, **kw)


# ---- 1 -----------------------------------------------------------------------------------------------------

def test_check1_passes_on_a_built_site(site):
    db, out, day = site
    r = data.check_numbers(ctx_for(db, day, out))
    assert r.status == "pass", r.problems
    assert r.numbers["holdings_compared"] >= 10 and r.numbers["call_cards_compared"] > 0


def test_check1_catches_a_changed_holding_value_and_names_the_stock(site):
    db, out, day = site
    body = read(out, "portfolio")
    body["holdings"][0]["value"] = round(body["holdings"][0]["value"] * 1.05)
    write(out, "portfolio", body)
    r = data.check_numbers(ctx_for(db, day, out))
    assert r.status == "fail" and body["holdings"][0]["symbol"] in " ".join(r.problems)


def test_check1_catches_a_wrong_gain_share_and_total(site):
    db, out, day = site
    body = read(out, "portfolio")
    body["holdings"][1]["gain_pct"] = 9.99
    body["holdings"][2]["share"] = 0.9
    body["total_value"] += 1_000_000
    write(out, "portfolio", body)
    r = data.check_numbers(ctx_for(db, day, out))
    text = " ".join(r.problems)
    assert "gain" in text and "share" in text and "portfolio total" in text


def test_check1_catches_a_wrong_call_chance_and_money(site):
    db, out, day = site
    calls = read(out, "calls")
    card = calls["buys"][0] if calls["buys"] else calls["sells"][0]
    card["probability"] = 0.99
    card["amount_inr"] = (card["amount_inr"] or 0) + 50_000
    write(out, "calls", calls)
    r = data.check_numbers(ctx_for(db, day, out))
    assert r.status == "fail" and card["symbol"] in " ".join(r.problems)


def test_check1_catches_tax_room_that_differs_from_the_stored_report(site):
    db, out, day = site
    stored = json.loads(db.execute("select payload from weekly_reports where section = 'tax' order by week_of desc limit 1").fetchone()[0])
    body = read(out, "portfolio")
    body["tax"] = {**body["tax"], "harvest_room": round(stored["harvest"]["gain_room"]) + 30000}
    write(out, "portfolio", body)
    r = data.check_numbers(ctx_for(db, day, out))
    assert any("harvest_room" in p for p in r.problems)


def test_check1_fails_without_a_site_folder(site):
    db, _, day = site
    assert data.check_numbers(ctx_for(db, day, None)).status == "fail"


# ---- 2 -----------------------------------------------------------------------------------------------------

def _book(db, kite_qty, lot_qty):
    db.execute("insert into stocks values ('TCS', 'Tata Consultancy Services', 'IT', 'INE467B01029')")
    db.execute("insert into holdings values ('2026-11-20 18:00:00', 'equity', 'TCS', 'INE467B01029', ?, 3000, 'kite')", [kite_qty])
    db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, source) values "
               "('stock', 'TCS', 'INE467B01029', '2024-01-02', ?, 3000, 'tradebook')", [lot_qty])


def test_check2_passes_when_lots_explain_kite(db):
    _book(db, 10, 10)
    r = data.check_units(ctx_for(db, DAY))
    assert r.status == "pass" and r.numbers == {"kite_holdings": 1, "mismatches": 0}


def test_check2_names_the_stock_when_units_differ(db):
    _book(db, 10, 7)
    r = data.check_units(ctx_for(db, DAY))
    assert r.status == "fail" and "TCS" in r.problems[0] and "3 unexplained" in r.problems[0]
    assert r.gaps[0].subject == "TCS"


def test_check2_fails_when_there_is_no_kite_snapshot(db):
    assert data.check_units(ctx_for(db, DAY)).status == "fail"


# ---- 3 -----------------------------------------------------------------------------------------------------

def _broken_series(db):
    insert_prices(db, price_rows("BROKEN", [100.0] * 90 + [4.0 * 5] * 30))
    db.execute("insert into stocks values ('BROKEN', 'Broken Ltd', 'X', 'INEBROKEN01')")


def test_check3_fails_on_an_unflagged_jump_and_passes_once_it_is_flagged(db):
    _broken_series(db)
    r = data.check_prices(ctx_for(db, DAY))
    assert r.status == "fail" and "BROKEN" in r.problems[0] and "-80%" in r.problems[0]
    flags.sync(db, DAY)
    r = data.check_prices(ctx_for(db, DAY))
    assert r.status == "pass" and r.numbers["flagged_series"] == 1
    assert [g.subject for g in r.gaps] == ["BROKEN"]          # it is listed for Health


def test_check3_gap_names_the_recorded_reason_for_a_flagged_series(db, tmp_path, monkeypatch):
    _broken_series(db)
    flags.sync(db, DAY)
    jump = flags.scan(db, DAY)[0].jump_date
    reasons = tmp_path / "reasons.json"
    reasons.write_text(json.dumps({f"BROKEN:{jump}": "Demerger on NSE feed: the price fell because a business moved to a new company."}))
    monkeypatch.setattr(flags, "REASONS_FILE", reasons)
    r = data.check_prices(ctx_for(db, DAY))
    assert "business moved to a new company" in r.gaps[0].detail
    assert r.numbers["with_reason"] == 1
    monkeypatch.setattr(flags, "REASONS_FILE", tmp_path / "missing.json")
    r = data.check_prices(ctx_for(db, DAY))
    assert r.numbers["with_reason"] == 0 and "Reason not looked up yet" in r.gaps[0].detail


def test_check3_passes_when_a_corporate_action_explains_the_move(db):
    _broken_series(db)
    db.execute("insert into corporate_actions (symbol, ex_date, kind, numerator, denominator, source) values ('BROKEN', ?, 'split', 5, 1, 'nse')",
               [date(2026, 11, 20) - timedelta(days=42)])
    insert_prices(db, [])      # no-op, keeps the helper imported
    r = data.check_prices(ctx_for(db, DAY))
    assert r.status == "pass" and r.numbers["jumps"] == 0


def test_check3_fails_when_a_flagged_series_still_shows_on_the_site(db, tmp_path):
    _broken_series(db)
    flags.sync(db, DAY)
    site = tmp_path / "site"
    (site / "data" / "history").mkdir(parents=True)
    (site / "data" / "search.json").write_text(json.dumps([{"symbol": "BROKEN", "name": "Broken Ltd", "exchange": "NSE"}]))
    (site / "data" / "history" / "BROKEN.json").write_text("{}")
    (site / "data" / "portfolio.json").write_text(json.dumps({"holdings": [{"symbol": "BROKEN", "gain_pct": 0.5}]}))
    r = data.check_prices(ctx_for(db, DAY, site))
    text = " ".join(r.problems)
    assert r.status == "fail" and "search" in text and "price chart" in text and "shows a gain" in text


# ---- 4 -----------------------------------------------------------------------------------------------------

def _fresh_db(db, last):
    insert_prices(db, price_rows("TCS", [100.0] * 5, end=last))
    db.execute("insert into index_levels values (?, 'Nifty 50', 25000, 20, 3, 1)", [last])
    db.execute("insert into navs values (?, 1, 100)", [last])
    db.execute("insert into fx values (?, 'USDINR', 83)", [last])
    db.execute("insert into delivery values (?, 'TCS', 'EQ', 1, 40)", [last])
    db.execute("insert into flows values (?, 'FII', 1, 1, 0)", [last])
    db.execute("insert into announcements values (?, 'TCS', 'x', '', '')", [datetime.combine(last, datetime.min.time())])
    db.execute("insert into headlines values ('TCS', ?, 't', 's', 'u', ?)", [datetime.combine(last, datetime.min.time()), last])
    db.execute("insert into holdings values (?, 'equity', 'TCS', 'I', 1, 1, 'kite')", [datetime.combine(last, datetime.min.time())])
    db.execute("insert into surveillance values (?, 'TCS', 'ASM')", [last])
    db.execute("insert into fundamentals values (?, 'TCS', 'pe', 20, 'y')", [last])
    db.execute("insert into quarterly (isin, symbol, period_end, consolidated, filed_at, revenue, operating_profit, net_profit, eps) "
               "values ('I', 'TCS', ?, true, ?, 1, 1, 1, 1)", [last, datetime.combine(last, datetime.min.time())])
    db.execute("insert into calls (made_on, symbol, kind, action, probability, base_rate, horizon_days) values (?, 'TCS', 'holding', 'hold', .5, .5, 91)", [last])


def test_check4_passes_when_every_source_is_current(db):
    _fresh_db(db, DAY)
    assert data.check_freshness(ctx_for(db, DAY)).status == "pass"


def test_check4_names_a_stale_source_and_records_a_gap(db):
    _fresh_db(db, DAY)
    db.execute("update prices set date = date - interval 10 day")
    r = data.check_freshness(ctx_for(db, DAY))
    assert r.status == "fail" and any(p.startswith("Prices:") for p in r.problems)
    assert any(g.subject == "Prices" and g.reason == "source_down" for g in r.gaps)


def test_check4_fails_when_the_site_calls_stale_data_current(db, tmp_path):
    _fresh_db(db, DAY)
    db.execute("update holdings set snapshot_at = snapshot_at - interval 20 day")
    site = tmp_path / "site"
    (site / "data").mkdir(parents=True)
    (site / "data" / "meta.json").write_text(json.dumps({"as_of": str(DAY), "status": {"ok": True, "text": "Everything is up to date."}}))
    r = data.check_freshness(ctx_for(db, DAY, site))
    assert any("Everything is up to date" in p for p in r.problems)


# ---- 5 -----------------------------------------------------------------------------------------------------

def test_check5_catches_nse_and_bse_closes_that_differ_and_only_notes_a_small_gap(db):
    insert_prices(db, price_rows("TCS", [100.0] * 3) + price_rows("TCS", [102.0] * 3, exchange="BSE")           # 2%: two closing auctions
                  + price_rows("INFY", [100.0] * 3) + price_rows("INFY", [90.0] * 3, exchange="BSE")         # 11%: a wrong price
                  + price_rows("THIN", [100.0] * 3) + price_rows("THIN", [50.0] * 3, exchange="BSE", value=1e5))   # BSE barely traded
    r = data.check_cross_source(ctx_for(db, DAY))
    assert r.status == "fail" and r.numbers["nse_bse_pairs"] == 2
    assert len(r.problems) == 1 and "INFY" in r.problems[0]
    assert len(r.notes) == 1 and "TCS" in r.notes[0]


def test_check5_passes_on_agreeing_exchanges(db):
    insert_prices(db, price_rows("TCS", [100.0] * 3) + price_rows("TCS", [100.5] * 3, exchange="BSE"))
    assert data.check_cross_source(ctx_for(db, DAY)).status == "pass"


def test_check5_catches_a_sector_index_that_disagrees_with_its_stocks(db):
    rows = []
    for i in range(6):
        rows += price_rows(f"IT{i}", [100.0, 101.0])
        db.execute("insert into stocks values (?, ?, 'Information Technology', ?)", [f"IT{i}", f"IT{i}", f"INE{i}"])
    insert_prices(db, rows)
    prev = DAY - timedelta(days=1)
    day = db.execute("select max(date) from prices").fetchone()[0]
    before = db.execute("select max(date) from prices where date < ?", [day]).fetchone()[0]
    db.execute("insert into index_levels values (?, 'Nifty IT', 100, null, null, null), (?, 'Nifty IT', 110, null, null, null)", [before, day])
    ctx = ctx_for(db, DAY, sector_index={"Information Technology": "Nifty IT"})
    r = data.check_cross_source(ctx)
    assert r.status == "fail" and "Nifty IT" in " ".join(r.problems)
    db.execute("update index_levels set close = 101 where date = ?", [day])
    assert data.check_cross_source(ctx).status == "pass"


def test_check5_catches_a_fund_value_that_is_not_units_times_nav(site):
    db, out, day = site
    assert data.check_cross_source(ctx_for(db, day, out)).status == "pass"
    body = read(out, "portfolio")
    fund = next(h for h in body["holdings"] if h["kind"] == "mf")
    fund["value"] = round(fund["value"] * 1.2)
    write(out, "portfolio", body)
    r = data.check_cross_source(ctx_for(db, day, out))
    assert r.status == "fail" and fund["symbol"] in " ".join(r.problems)


# ---- 6 -----------------------------------------------------------------------------------------------------

def test_check6_passes_on_a_built_site_and_on_the_previous_days_site(site_built):
    db, out, day = site_built
    r = data.check_schema(ctx_for(db, day, out, previous_site=out))
    assert r.status == "pass", r.problems[:5]
    assert r.numbers["files"] > 20


def test_check6_catches_a_missing_always_field_a_null_and_a_wrong_type(site):
    db, out, day = site
    stock = sorted((out / "data" / "stock").glob("*.json"))[0]
    body = json.loads(stock.read_text())
    del body["close"]
    body["name"] = None
    body["change_pct"] = "up"
    stock.write_text(json.dumps(body))
    r = data.check_schema(ctx_for(db, day, out))
    text = " ".join(r.problems)
    assert r.status == "fail" and "close is missing" in text and "name is null" in text and "change_pct" in text and "contract says num" in text


def test_check6_catches_a_stock_without_its_files_and_a_broken_previous_day(site, tmp_path):
    db, out, day = site
    (out / "data" / "history" / "TCS.json").unlink()
    old = tmp_path / "old"
    shutil.copytree(out, old)
    flows = json.loads((old / "data" / "flows.json").read_text())
    del flows["days"]
    (old / "data" / "flows.json").write_text(json.dumps(flows))
    r = data.check_schema(ctx_for(db, day, out, previous_site=old))
    text = " ".join(r.problems)
    assert "no history or stock file" in text and "previous day: flows.json: days is missing" in text
