"""Lane R item 4: a US share the owners hold (ServiceNow, from `usprices`, exchange NYSE) has a split-adjusted dollar series in its dossier."""
from datetime import date, timedelta

from stockpilot import dossier, store

DAY = date(2026, 11, 24)


def seed(db, with_split=True):
    rows = []
    for i in range(200):
        d = DAY - timedelta(days=i)
        raw = 100.0 if d >= date(2026, 6, 1) else 500.0           # five-for-one on 2026-06-01: raw closes before it are 5x
        rows.append((d, "NOW", "NYSE", "EQ", raw, raw + 1, raw - 1, raw, None, 1000, None, None))
    db.executemany("insert into prices values (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    if with_split:
        db.execute("insert into corporate_actions (symbol, isin, ex_date, kind, numerator, denominator, subject, source) "
                   "values ('NOW', 'US81762P1021', '2026-06-01', 'split', 5, 1, 'split', 'fidelity')")


def test_the_dossier_of_a_us_share_has_prices_in_dollars_split_adjusted(tmp_path):
    db = store.open(tmp_path / "s.duckdb")
    seed(db)
    rows = dossier._daily(db, "NOW", DAY)
    assert rows and len(rows) > 150
    assert {round(r[3], 2) for r in rows} == {100.0}                       # the pre-split closes are divided by five
    assert dossier.build(db, "NOW", DAY)["price"]


def test_an_nse_series_still_wins_over_a_us_one(tmp_path):
    db = store.open(tmp_path / "s.duckdb")
    seed(db)
    db.execute("insert into prices values (?, 'NOW', 'NSE', 'EQ', 7, 8, 6, 7, null, 10, 70, 1)", [DAY])
    assert [r[3] for r in dossier._daily(db, "NOW", DAY)] == [7.0]
