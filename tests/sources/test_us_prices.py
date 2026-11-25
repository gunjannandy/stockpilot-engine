"""US prices for Schedule FA: NOW daily closes into prices (exchange NYSE), USD/INR for the window, then the schedule fills."""
import json
from datetime import date

import pytest

from stockpilot import store, weekly

from stockpilot.sources import fx, usprices

from stockpilot.analysis import tax

FIXTURE = json.loads(open(__file__.replace("sources/test_us_prices.py", "fixtures/us_prices_now.json")).read())


def fake_history(symbols, start):
    assert list(symbols) == ["NOW"]            # one batch, every symbol at once
    return {s: [(date.fromisoformat(d), *v) for d, v in FIXTURE[s].items()] for s in symbols}


def _db(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, currency) "
               "values ('rsu', 'NOW', 'US81762P1021', '2025-02-10', 10, 100, 'USD')")
    return db


def test_first_vest_year_comes_from_the_foreign_lots(tmp_path):
    db = _db(tmp_path)
    assert usprices.first_year(db) == 2025
    assert usprices.symbols(db) == ["NOW"]


def test_ingest_stores_closes_as_nyse_and_is_repeatable(tmp_path):
    db = _db(tmp_path)
    assert usprices.refresh(db, fake_history, date(2026, 1, 15)) == 5
    assert usprices.refresh(db, fake_history, date(2026, 1, 15)) == 5
    rows = db.execute("select date, close from prices where symbol='NOW' and exchange='NYSE' order by date").fetchall()
    assert len(rows) == 5 and rows[0] == (date(2025, 12, 29), 1000.0)


def test_fetch_asks_from_the_first_vest_year(tmp_path):
    db = _db(tmp_path)
    seen = {}
    usprices.refresh(db, lambda s, start: seen.update(start=start) or {}, date(2026, 1, 15))
    assert seen["start"] == date(2025, 1, 1)


def test_no_foreign_lots_means_no_fetch(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert usprices.refresh(db, lambda *a: pytest.fail("fetched"), date(2026, 1, 15)) == 0


def test_frankfurter_range_fills_the_fx_table(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    body = json.dumps({"rates": {"2025-12-29": {"INR": 90.0}, "2025-12-30": {"INR": 91.0}}}).encode()
    urls = []
    assert fx.ingest_usdinr_range(db, date(2025, 12, 29), date(2025, 12, 31), lambda u: urls.append(u) or body) == 2
    assert len(urls) == 1 and "2025-12-29..2025-12-31" in urls[0]
    assert fx.usdinr_on(db, date(2025, 12, 31)) == 91.0


def test_sbi_rate_wins_over_frankfurter_when_the_owner_supplied_one(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    db.execute("insert into fx values ('2025-12-30', 'USDINR', 91.0)")
    rate_on = fx.rate_on(db)
    assert rate_on(date(2025, 12, 30)) == 91.0 and fx.source_note(db, date(2025, 12, 30)).startswith("Frankfurter")
    db.execute("insert into fx values ('2025-12-30', 'USDINR_SBI', 90.5)")
    assert fx.rate_on(db)(date(2025, 12, 30)) == 90.5 and fx.source_note(db, date(2025, 12, 30)).startswith("SBI")


def test_schedule_fa_peak_and_closing_fill_from_ingested_prices(tmp_path):
    db = _db(tmp_path)
    usprices.refresh(db, fake_history, date(2026, 1, 15))
    for d, r in (("2025-02-10", 85.0), ("2025-12-29", 90.0), ("2025-12-30", 90.0), ("2025-12-31", 90.0)):
        db.execute("insert or replace into fx values (?, 'USDINR', ?)", [d, r])
    lots = [dict(zip(["id", "kind", "symbol", "isin", "acquired_on", "quantity", "cost_per_unit", "currency"], r))
            for r in db.execute("select id, kind, symbol, isin, acquired_on, quantity, cost_per_unit, currency from lots").fetchall()]
    [row] = tax.schedule_fa(lots, [], 2025, weekly._closes(db, {"NOW"}, 2025), fx.rate_on(db))
    assert row["note"] == "" and row["peak_value"] == pytest.approx(10 * 1100 * 90.0)    # peak close 1100 on 30 Dec
    assert row["closing_value"] == pytest.approx(10 * 1050 * 90.0)


def test_the_pack_readme_names_the_fx_source(tmp_path):
    db = _db(tmp_path)
    db.execute("insert into fx values ('2025-02-10', 'USDINR', 85.0), ('2025-12-31', 'USDINR', 90.0)")
    out = weekly.tax_section(db, date(2026, 1, 15), tmp_path / "pack", {"carried": [], "slab_income": 0.0, "fmv_2018": {}})
    readme = (tmp_path / "pack" / "2025-26" / "README.txt").read_text()
    assert "Frankfurter" in readme and "SBI TT buying rate" in readme
