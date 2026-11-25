"""Harvest room, Schedule FA and the ITR pack, built on the tax maths."""
import csv
import json
from datetime import date

from stockpilot.analysis import tax

AS_OF = date(2026, 11, 22)
RULES = tax.rules_for(2026)


def _lot(id, day, qty, cost, symbol="ABC", kind="equity", currency="INR", isin=None):
    return {"id": id, "kind": kind, "symbol": symbol, "isin": isin or f"INE-{symbol}", "acquired_on": day,
            "quantity": qty, "cost_per_unit": cost, "currency": currency}


def test_open_lots_are_what_the_sales_left_behind():
    lots = [_lot(1, date(2025, 1, 1), 10, 100), _lot(2, date(2025, 3, 1), 10, 120)]
    sale = {"kind": "equity", "symbol": "ABC", "isin": "INE-ABC", "sold_on": date(2026, 6, 1), "quantity": 15,
            "price_per_unit": 150, "currency": "INR", "expenses": 0}
    left = tax.open_lots(lots, [sale])
    assert [(l["id"], l["quantity"]) for l in left] == [(2, 5)]


def test_harvest_books_long_term_gain_up_to_the_unused_exemption_and_stops_at_a_young_lot():
    lots = [_lot(1, date(2024, 1, 1), 1000, 100), _lot(2, date(2026, 5, 1), 1000, 100)]
    out = tax.harvest(lots, {"ABC": 200.0}, AS_OF, RULES, realised_ltcg_equity=50_000)
    assert out["gain_room"] == 75_000
    [c] = out["gain_candidates"]
    assert (c["symbol"], c["quantity"], c["gain"]) == ("ABC", 750, 75_000)
    assert out["gain_room_left"] == 0


def test_harvest_room_is_zero_once_the_exemption_is_used():
    lots = [_lot(1, date(2024, 1, 1), 1000, 100)]
    out = tax.harvest(lots, {"ABC": 200.0}, AS_OF, RULES, realised_ltcg_equity=130_000)
    assert out["gain_room"] == 0 and out["gain_candidates"] == []


def test_harvest_lists_losers_with_the_loss_a_full_sale_books():
    lots = [_lot(1, date(2025, 6, 1), 100, 100, symbol="XYZ"), _lot(2, date(2026, 2, 1), 100, 80, symbol="XYZ")]
    out = tax.harvest(lots, {"XYZ": 70.0}, AS_OF, RULES, realised_ltcg_equity=0)
    [c] = out["loss_candidates"]
    assert (c["symbol"], c["quantity"], c["loss"]) == ("XYZ", 200, 4_000)


def test_schedule_fa_gives_initial_peak_closing_and_proceeds_in_rupees():
    lots = [_lot(1, date(2025, 3, 15), 10, 200, symbol="NOW", kind="foreign", currency="USD", isin="US81762P1021")]
    sales = [{"kind": "foreign", "symbol": "NOW", "isin": "US81762P1021", "sold_on": date(2026, 3, 10),
              "quantity": 4, "price_per_unit": 240, "currency": "USD", "expenses": 0}]
    closes = {date(2026, 1, 2): 210.0, date(2026, 3, 1): 250.0, date(2026, 12, 31): 230.0}
    [row] = tax.schedule_fa(lots, sales, 2026, closes={"NOW": closes}, rate_on=lambda d: 90.0)
    assert row["initial_value"] == 10 * 200 * 90
    assert row["peak_value"] == 10 * 250 * 90
    assert row["closing_value"] == 6 * 230 * 90
    assert row["gross_proceeds"] == 4 * 240 * 90
    assert row["units_at_close"] == 6


def test_schedule_fa_skips_stock_held_only_in_india_and_flags_missing_prices():
    lots = [_lot(1, date(2025, 3, 15), 10, 200, symbol="NOW", kind="foreign", currency="USD"),
            _lot(2, date(2025, 3, 15), 10, 200, symbol="ABC")]
    [row] = tax.schedule_fa(lots, [], 2026, closes={}, rate_on=lambda d: 90.0)
    assert row["symbol"] == "NOW" and row["peak_value"] is None and "price history" in row["note"]


def test_financial_year_labels():
    assert tax.fy_of(date(2026, 3, 31)) == 2025 and tax.fy_of(date(2026, 4, 1)) == 2026
    assert tax.fy_label(2026) == "2026-27"


def test_pack_writes_schedule_112a_and_summary_files(tmp_path):
    lots = [_lot(1, date(2024, 1, 1), 100, 100)]
    sale = {"kind": "equity", "symbol": "ABC", "isin": "INE-ABC", "sold_on": date(2026, 6, 1), "quantity": 100,
            "price_per_unit": 300, "currency": "INR", "expenses": 20}
    pack = tax.build_pack(lots, [sale], 2026, tmp_path, rate_on=lambda d: None, closes={})
    rows = list(csv.DictReader((tmp_path / "schedule_112a.csv").open()))
    assert rows[0]["isin"] == "INE-ABC" and float(rows[0]["gain"]) == 19_980
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["fy"] == "2026-27" and summary["ltcg_equity"] == 19_980
    assert summary["tax"]["total"] == 0 and pack["itr_form"] == "ITR-2"
    assert (tmp_path / "README.txt").exists()
