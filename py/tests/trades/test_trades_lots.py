from datetime import date
from pathlib import Path

from stockpilot import store
from stockpilot.trades import corporate_actions, lots, tradebook

FIX = Path(__file__).parents[1] / "fixtures" / "trades"
REL = "INE002A01018"


def seed(db):
    trades = tradebook.parse(FIX.joinpath("tradebook.csv").read_text())
    lots.save_trades(db, trades)
    corporate_actions.save(db, [
        corporate_actions.Action("RELIANCE", REL, date(2023, 9, 1), "split", 2, 1, "Split"),
        corporate_actions.Action("RELIANCE", REL, date(2024, 2, 1), "bonus", 1, 1, "Bonus 1:1"),
    ])
    return lots.rebuild(db)


def test_tradebook_skips_non_equity_rows():
    trades = tradebook.parse(FIX.joinpath("tradebook.csv").read_text())
    assert len(trades) == 6
    assert {t.symbol for t in trades} == {"RELIANCE", "INFY"}


def test_tradebook_mutual_fund_rows_are_mf_buys_keyed_like_the_coin_mail():
    got = tradebook.parse(FIX.joinpath("tradebook_mf.csv").read_text())
    assert [(t.kind, t.side, t.quantity, t.price, t.trade_key) for t in got] == [
        ("mf", "buy", 234.962, 85.1159, "mf:2025-04-02:INF879O01027:buy:234.962"),
        ("mf", "buy", 215.789, 92.6786, "mf:2025-07-01:INF879O01027:buy:215.789")]


def test_tradebook_to_lots_to_holdings_matches_hand_example(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    result = seed(db)
    assert result.unmatched_sells == []
    rows = db.execute(
        "select acquired_on, quantity, cost_per_unit, closed_quantity from lots "
        "where isin = ? order by acquired_on, id", [REL]).fetchall()
    assert rows == [
        (date(2023, 1, 10), 20.0, 50.0, 20.0),   # 10 -> split x2; 16 sold in June (8x2), 4 in April
        (date(2023, 3, 15), 10.0, 60.0, 10.0),
        (date(2024, 2, 1), 14.0, 0.0, 6.0),      # bonus 1:1 on the 14 held, 6 sold FIFO in April
        (date(2024, 3, 1), 6.0, 70.0, 0.0),
    ]
    held = {h.isin: h for h in lots.holdings(db)}
    assert held[REL].quantity == 14.0
    assert held[REL].avg_cost == 30.0   # (8 bonus shares at 0 + 6 at 70) / 14
    assert held["INE009A01021"].quantity == 7.0 and held["INE009A01021"].avg_cost == 1500.0


def test_rebuild_and_save_are_idempotent(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    seed(db)
    first = db.execute("select count(*), sum(quantity - closed_quantity) from lots").fetchone()
    seed(db)
    assert db.execute("select count(*), sum(quantity - closed_quantity) from lots").fetchone() == first
    assert db.execute("select count(*) from trades").fetchone()[0] == 6


def test_same_trade_from_two_sources_counts_once(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    t = tradebook.parse(FIX.joinpath("tradebook.csv").read_text())[0]
    import dataclasses
    dup = dataclasses.replace(t, source="contract_note")
    assert lots.save_trades(db, [t]) == 1
    assert lots.save_trades(db, [dup]) == 0


def test_sell_without_buy_is_reported_not_invented(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    lots.save_trades(db, [lots.Trade("tradebook", "X1", "stock", "TCS", "INE467B01029", "sell",
                                     date(2024, 1, 5), 4, 3500)])
    result = lots.rebuild(db)
    assert result.unmatched_sells == [("INE467B01029", date(2024, 1, 5), 4.0)]
    assert db.execute("select count(*) from lots").fetchone()[0] == 0


def test_rebuild_leaves_expected_vests_out_of_lots(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    lots.save_trades(db, [
        lots.Trade("fidelity", "V1", "rsu", "NOW", "US81762P1021", "vest", date(2026, 8, 15), 10, 800.0,
                   currency="USD"),
        lots.Trade("rsu_inference", "E1", "rsu", "NOW", "US81762P1021", "vest", date(2026, 11, 15), 10, None,
                   currency="USD", status="expected"),
    ])
    lots.rebuild(db)
    assert db.execute("select count(*), min(currency) from lots").fetchone() == (1, "USD")


def test_nse_corporate_action_subjects():
    parse = corporate_actions.from_nse
    split = parse({"symbol": "X", "subject": "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share",
                   "exDate": "01-Sep-2023"})
    assert (split.kind, split.numerator, split.denominator, split.ex_date) == ("split", 5, 1, date(2023, 9, 1))
    bonus = parse({"symbol": "X", "subject": "Bonus 3:2", "exDate": "05-Feb-2024"})
    assert (bonus.kind, bonus.numerator, bonus.denominator) == ("bonus", 3, 2)
    assert parse({"symbol": "X", "subject": "Dividend - Rs 5 Per Share", "exDate": "05-Feb-2024"}) is None


def test_credit_is_a_split_or_bonus_not_a_buy():
    actions = [corporate_actions.Action("X", "INX", date(2024, 2, 5), "bonus", 1, 2, "Bonus 1:2"),
               corporate_actions.Action("X", "INX", date(2023, 9, 1), "split", 5, 1, "Split")]
    classify = corporate_actions.classify_credit
    assert classify(actions, "INX", date(2024, 2, 6), 50, held_before=100) == "bonus"
    assert classify(actions, "INX", date(2023, 9, 2), 400, held_before=100) == "split"
    assert classify(actions, "INX", date(2024, 2, 6), 30, held_before=100) == "buy"
    assert classify(actions, "INX", date(2022, 1, 1), 50, held_before=100) == "buy"




def _t(symbol, isin, side, day, qty, price):
    return lots.Trade("contract_note", f"{symbol}{day}", "stock", symbol, isin, side, day, qty, price)


def test_a_split_that_changed_the_isin_still_matches_old_buys_to_new_sells(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    lots.save_trades(db, [_t("CANBK", "INE476A01014", "buy", date(2024, 1, 2), 100, 500.0),
                          _t("CANBK", "INE476A01022", "sell", date(2024, 9, 5), 445, 105.0)])
    corporate_actions.save(db, [corporate_actions.Action("CANBK", "INE476A01014", date(2024, 5, 15), "split", 5, 1, "Split")])
    assert lots.rebuild(db).unmatched_sells == []
    assert [(h.isin, h.quantity) for h in lots.holdings(db)] == [("INE476A01022", 55.0)]


def test_a_series_suffix_on_the_symbol_does_not_hide_a_bonus(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    lots.save_trades(db, [_t("NBCC-A", "INE095N01031", "buy", date(2024, 1, 2), 100, 150.0)])
    corporate_actions.save(db, [corporate_actions.Action("NBCC", "INE095N01015", date(2024, 10, 7), "bonus", 1, 2, "Bonus")])
    lots.rebuild(db)
    assert [(h.symbol, h.quantity) for h in lots.holdings(db)] == [("NBCC", 150.0)]


def test_lots_bought_before_an_isin_change_carry_the_current_isin(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    db.execute("insert into stocks (symbol, name, isin) values ('CESC', 'CESC', 'INE486A01021')")
    lots.save_trades(db, [_t("CESC", "INE486A01013", "buy", date(2020, 1, 2), 20, 600.0)])
    lots.rebuild(db)
    assert [(h.isin, h.quantity) for h in lots.holdings(db)] == [("INE486A01021", 20.0)]


def test_a_renamed_company_and_a_spaced_series_suffix_are_one_holding(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    lots.save_trades(db, [_t("TWL", "INE615H01020", "buy", date(2023, 6, 16), 41, 424.0),
                          _t("TITAGARH", "INE615H01020", "sell", date(2023, 9, 15), 41, 764.0),
                          _t("JSL", "INE220G01021", "buy", date(2022, 5, 6), 50, 164.0),
                          _t("JSL - A", "INE220G01021", "buy", date(2022, 5, 27), 100, 117.0)])
    assert lots.rebuild(db).unmatched_sells == []
    assert [(h.symbol, h.quantity) for h in lots.holdings(db)] == [("JSL", 150.0)]
