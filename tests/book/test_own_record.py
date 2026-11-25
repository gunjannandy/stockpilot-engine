import json
from datetime import date

from helpers import insert_prices
from stockpilot import store
from stockpilot.calls import brief
from stockpilot.book import record
from stockpilot.trades import lots, smallcase
from stockpilot.trades.lots import Trade

AS_OF = date(2025, 12, 31)


def trade(symbol, side, qty, price, day):
    key = f"{symbol}{day}{side}"
    return Trade("contract_note", key, "stock", symbol, f"INE{symbol}00000"[:12], side, day, qty, price, trade_key=key)


def close(symbol, day, value):
    return (day, symbol, "NSE", "EQ", value, value, value, value, value, 1000, 1e6, 10)


def seed(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    buy = date(2025, 1, 10)
    lots.save_trades(db, [
        trade("XXX", "buy", 10, 100, buy), trade("XXX", "sell", 10, 130, date(2025, 3, 10)),     # winner, 59 days
        trade("YYY", "buy", 10, 100, buy), trade("YYY", "sell", 10, 120, date(2025, 2, 10)),     # winner, 31 days
        trade("ZZZ", "buy", 10, 100, buy), trade("ZZZ", "sell", 10, 80, date(2025, 7, 10)),      # loser, 181 days
        trade("SSS", "buy", 5, 50, buy), trade("SSS", "sell", 5, 70, date(2025, 4, 10))])        # smallcase: not his
    db.execute("insert into smallcase_orders values ('o1', 'Value', '2025-01-10', 'SSS', 'buy', 5, 50, 'm'),"
               " ('o2', 'Value', '2025-04-10', 'SSS', 'sell', 5, 70, 'm')")
    smallcase.tag_trades(db)
    lots.rebuild(db)
    insert_prices(db, [close("XXX", date(2025, 6, 9), 150), close("YYY", date(2025, 5, 12), 110)])   # 91 days after each sale
    for day, level in [(buy, 20000), (date(2025, 2, 10), 20400), (date(2025, 3, 10), 21000), (date(2025, 7, 10), 19000)]:
        db.execute("insert into index_levels values (?, 'Nifty 50', ?, 20, 3, 1)", [day, level])
    return db


def test_own_record_counts_only_his_trades(tmp_path):
    got = record.build(seed(tmp_path), AS_OF)
    assert got["closed"] == 3 and got["winners"] == 2 and got["losers"] == 1
    assert got["win_rate"] == 66.7
    assert (got["avg_days_winners"], got["avg_days_losers"]) == (45.0, 181.0)


def test_how_often_a_winner_was_sold_before_its_next_three_months_gain(tmp_path):
    got = record.build(seed(tmp_path), AS_OF)
    assert got["sold_early"] == {"checked": 2, "rose_after": 1, "share": 50.0}


def test_against_the_nifty_over_each_holding_period(tmp_path):
    got = record.build(seed(tmp_path), AS_OF)
    assert got["vs_nifty"] == {"checked": 3, "beat": 2, "share": 66.7, "average_gap_points": 9.33}


def test_months_list_what_closed_when(tmp_path):
    got = record.build(seed(tmp_path), AS_OF)
    assert got["by_month"] == [{"month": "2025-02", "closed": 1, "winners": 1, "gain": 200.0},
                               {"month": "2025-03", "closed": 1, "winners": 1, "gain": 300.0},
                               {"month": "2025-07", "closed": 1, "winners": 0, "gain": -200.0}]


def test_two_plain_lines_about_him_and_no_stock_named(tmp_path):
    lines = record.build(seed(tmp_path), AS_OF)["lines"]
    assert len(lines) == 2
    assert lines[0] == "Of the 3 stock trades you closed, 67% made money. Winners were held 45 days on average, losers 181."
    assert lines[1] == "Half of the winners you sold went on to gain more within the next 3 months."
    assert not any(s in " ".join(lines) for s in ("XXX", "YYY", "ZZZ"))


def test_too_few_trades_gives_no_lines(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    got = record.build(db, AS_OF)
    assert got["closed"] == 0 and got["lines"] == [] and got["win_rate"] is None


def test_write_makes_the_site_file(tmp_path):
    db = seed(tmp_path)
    record.write(db, tmp_path / "site", AS_OF)
    body = json.loads((tmp_path / "site" / "data" / "own_record.json").read_text())
    assert body["closed"] == 3
