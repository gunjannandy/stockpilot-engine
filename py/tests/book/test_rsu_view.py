"""Lane R item 3 (data): everything the RSU pane and the ServiceNow page need, in one object. Made-up numbers."""
from datetime import date

from pytest import approx

from stockpilot import store
from stockpilot.book import rsu_view
from stockpilot.trades import lots

ISIN = "US81762P1021"
TODAY = date(2026, 11, 25)


def seed(db):
    for d in (date(2024, 8, 17), date(2026, 5, 17), date(2026, 11, 25), date(2026, 11, 24)):
        db.execute("insert into fx values (?, 'USDINR', 80.0)", [d])
    db.execute("insert into fidelity_lots values ('2025-12-31', 'NOW', ?, '2024-08-17', 10, 80000, 8000, 90000, 10000, null, null, 'long')", [ISIN])
    lots.save_trades(db, [lots.Trade("fidelity_docs", "v", "rsu", "NOW", ISIN, "vest", date(2026, 5, 17), 4.0, 100.0, "USD", trade_key="v")])
    db.execute("insert into fidelity_holdings values ('2026-11-24', 'NOW', ?, 16, 130000, 1.0, 100)", [ISIN])
    lots.rebuild(db)


def test_cost_profit_and_value_in_rupees(tmp_path):
    db = store.open(tmp_path / "s.duckdb")
    seed(db)
    v = rsu_view.build(db, TODAY, price_usd=110.0, portfolio_value=200_000.0, max_single=0.08)
    assert v["shares"] == 16 and v["cost_inr"] == approx(130000) and v["value_inr"] == approx(16 * 110 * 80)
    assert v["profit_inr"] == approx(16 * 110 * 80 - 130000) and v["share_of_portfolio"] == approx(16 * 110 * 80 / 200000, abs=1e-3)


def test_lots_say_whether_they_are_real_and_when_they_turn_long_term(tmp_path):
    db = store.open(tmp_path / "s.duckdb")
    seed(db)
    v = rsu_view.build(db, TODAY, price_usd=110.0, portfolio_value=200_000.0, max_single=0.08)
    by = {l["acquired_on"]: l for l in v["lots"]}
    assert by["2024-08-17"]["origin"] == "statement" and by["2024-08-17"]["term"] == "long"       # 24 months passed on 2026-08-18
    assert by["2026-05-17"]["origin"] == "document" and by["2026-05-17"]["term"] == "short"
    assert by["2026-05-17"]["turns_long_term_on"] == "2028-05-18"
    assert v["statement"]["as_of"] == "2025-12-31" and v["statement"]["real_shares"] == 14 and v["statement"]["estimated_shares"] == 2


def test_tax_if_sold_uses_the_foreign_rates_with_cess(tmp_path):
    db = store.open(tmp_path / "s.duckdb")
    seed(db)
    v = rsu_view.build(db, TODAY, price_usd=110.0, portfolio_value=200_000.0, max_single=0.08)
    long_gain = 10 * 110 * 80 - 80000                     # the 2024 lot
    t = v["tax_if_sold"]["all"]
    assert t["long_gain_inr"] == approx(long_gain) and t["tax_inr"] > 0
    assert t["tax_inr"] == approx(long_gain * 0.125 * 1.04 + t["short_gain_inr"] * 0.30 * 1.04)


def test_trim_call_names_shares_and_the_tax_and_is_never_an_order(tmp_path):
    db = store.open(tmp_path / "s.duckdb")
    seed(db)
    v = rsu_view.build(db, TODAY, price_usd=110.0, portfolio_value=200_000.0, max_single=0.08)
    call = v["call"]
    value, price = 16 * 110 * 80, 110 * 80
    shares = -(-(value - 0.08 * 200000) // (0.92 * price))        # ceil
    assert call["stance"] == "trim" and call["shares"] == shares
    assert "limit" in call["why"] and "₹" in call["tax_line"] and "order" not in (call["why"] + call["tax_line"]).lower()
    assert call["sells_oldest_first"] is True


def test_no_call_when_under_the_limit(tmp_path):
    db = store.open(tmp_path / "s.duckdb")
    seed(db)
    v = rsu_view.build(db, TODAY, price_usd=110.0, portfolio_value=20_000_000.0, max_single=0.08)
    assert v["call"] is None


def test_none_when_there_are_no_rsu_lots(tmp_path):
    assert rsu_view.build(store.open(tmp_path / "s.duckdb"), TODAY, price_usd=1.0, portfolio_value=1.0, max_single=0.08) is None




def test_a_sale_at_a_loss_says_no_tax_and_names_the_loss(tmp_path):
    db = store.open(tmp_path / "s.duckdb")
    seed(db)
    v = rsu_view.build(db, TODAY, price_usd=60.0, portfolio_value=100_000.0, max_single=0.08)      # below cost: 16 x 60 x 80 = 76,800 vs 130,000
    assert v["call"]["tax_line"].startswith("Selling") and "no tax" in v["call"]["tax_line"] and "loss" in v["call"]["tax_line"]
    assert v["tax_if_sold"]["all"]["tax_inr"] == 0 and v["tax_if_sold"]["all"]["net_gain_inr"] < 0
