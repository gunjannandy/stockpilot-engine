from datetime import date, timedelta

from stockpilot import store

from stockpilot.analysis import quality
from helpers import insert_prices


def _row(day, symbol, close, prev=None):
    return (day, symbol, "NSE", "EQ", close, close, close, close, prev or close, 1000, close * 1000, 10)


def _days(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _db(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    days = _days(date(2026, 1, 5), 20)
    rows = []
    for i, d in enumerate(days):
        if d == days[7]:
            continue                                   # a missing day
        rows.append(_row(d, "OKAY", 100.0))
        if i < 10:
            rows.append(_row(d, "STALE", 50.0))        # stops early
        rows.append(_row(d, "JUMPY", 100.0 if i < 12 else 200.0, 100.0 if i <= 12 else 200.0))
    insert_prices(db, rows)
    db.executemany("insert into stocks values (?, ?, ?, ?)",
                   [(s, s, "x", s) for s in ("OKAY", "STALE", "JUMPY")])
    return db, days


def test_missing_trading_day_is_reported_unless_a_holiday(tmp_path):
    db, days = _db(tmp_path)
    assert quality.missing_days(db) == [days[7]]
    db.execute("insert into holidays values (?, 'x')", [days[7]])
    assert quality.missing_days(db) == []


def test_stale_symbol_still_listed(tmp_path):
    db, _ = _db(tmp_path)
    assert [s for s, _ in quality.stale_symbols(db)] == ["STALE"]


def test_jump_without_corporate_action_only(tmp_path):
    db, days = _db(tmp_path)
    assert [(s, d) for s, d, _ in quality.big_moves(db)] == [("JUMPY", days[12])]
    db.execute("insert into corporate_actions values ('JUMPY', 'x', ?, 'split', 2, 1, 's', 'nse')", [days[12]])
    assert quality.big_moves(db) == []


def test_report_is_written(tmp_path):
    db, _ = _db(tmp_path)
    path = quality.write_report(db, tmp_path / "quality.md")
    text = path.read_text()
    assert "Missing trading days" in text and "STALE" in text and "JUMPY" in text
