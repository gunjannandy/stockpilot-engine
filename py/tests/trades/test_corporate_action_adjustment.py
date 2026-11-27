"""Lane Q: corporate actions are the only source of adjustment factors."""
import json
from datetime import date, timedelta
from pathlib import Path

import pytest
from pytest import approx

from helpers import insert_prices
from stockpilot import store
from stockpilot.analysis import analytics, quality
from stockpilot.trades import corporate_actions as ca

FIXTURE = Path(__file__).parents[1] / "fixtures" / "nse_corporate_actions.json"


def weekdays(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def load(db, symbol, days, closes, value=3e7):
    """Rows where prev_close is the raw previous close, as NSE's unadjusted bhavcopy file shows it."""
    rows = [(d, symbol, "NSE", "EQ", c, c, c, c, closes[i - 1] if i else c, 1000, value, 10)
            for i, (d, c) in enumerate(zip(days, closes))]
    insert_prices(db, rows)


def action(db, symbol, ex, kind, num, den, source="nse"):
    db.execute("insert into corporate_actions (symbol, isin, ex_date, kind, numerator, denominator, subject, source) "
               "values (?, null, ?, ?, ?, ?, 's', ?)", [symbol, ex, kind, num, den, source])


def test_a_one_for_five_split_gives_a_continuous_series_and_the_right_12m_return(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    days = weekdays(date(2025, 1, 6), 270)
    k = 140
    # SHRIRAMFIN-style: the raw close falls 81% on the ex-date, while the real stock rose 0.1% a day
    real = [100 * 1.001 ** i for i in range(270)]
    raw = [c * (5 if i < k else 1) for i, c in enumerate(real)]
    load(db, "SPLITCO", days, raw)
    action(db, "SPLITCO", days[k], "split", 5, 1)
    adj = dict(analytics.adjusted_closes(db, "SPLITCO", since=days[0]))
    assert adj[days[k - 1]] == approx(real[k - 1])
    assert adj[days[k]] == approx(real[k])                 # the ex-date row itself is unchanged
    f = analytics.price_factors(db, as_of=days[-1])["SPLITCO"]
    assert f["ret_12m"] == approx(1.001 ** 252 - 1, rel=1e-6)
    assert f["max_dd_1y"] == approx(0, abs=1e-9)


def test_a_one_for_one_bonus_halves_history(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    days = weekdays(date(2026, 1, 5), 10)
    load(db, "BON", days, [200, 200, 200, 200, 200, 100, 100, 100, 100, 100])
    action(db, "BON", days[5], "bonus", 1, 1)               # (1 + 1) / 1 = 2
    adj = dict(analytics.adjusted_closes(db, "BON", since=days[0]))
    assert [adj[d] for d in days] == approx([100.0] * 10)


def test_two_actions_on_one_day_multiply(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    days = weekdays(date(2026, 1, 5), 6)
    load(db, "BOTH", days, [400, 400, 400, 100, 100, 100])
    action(db, "BOTH", days[3], "split", 2, 1)
    action(db, "BOTH", days[3], "bonus", 1, 1)              # 2 * 2 = 4
    adj = dict(analytics.adjusted_closes(db, "BOTH", since=days[0]))
    assert [adj[d] for d in days] == approx([100.0] * 6)


def test_two_actions_on_different_days_both_apply_to_older_rows(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    days = weekdays(date(2026, 1, 5), 6)
    load(db, "TWICE", days, [400, 400, 200, 200, 100, 100])
    action(db, "TWICE", days[2], "split", 2, 1)
    action(db, "TWICE", days[4], "split", 2, 1)
    adj = dict(analytics.adjusted_closes(db, "TWICE", since=days[0]))
    assert [adj[d] for d in days] == approx([100.0] * 6)


def test_a_crash_with_no_action_stays_a_crash(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    days = weekdays(date(2026, 1, 5), 8)
    load(db, "CRASH", days, [100, 100, 100, 100, 20, 20, 20, 20])
    adj = dict(analytics.adjusted_closes(db, "CRASH", since=days[0]))
    assert adj[days[3]] == approx(100) and adj[days[4]] == approx(20)
    assert [(s, d) for s, d, _ in quality.big_moves(db)] == [("CRASH", days[4])]


def test_other_symbols_and_other_kinds_are_untouched(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    days = weekdays(date(2026, 1, 5), 4)
    load(db, "A", days, [100, 100, 50, 50])
    load(db, "B", days, [100, 100, 100, 100])
    action(db, "A", days[2], "split", 2, 1)
    action(db, "B", days[2], "dividend", 0, 0)
    assert [c for _, c in analytics.adjusted_closes(db, "B", since=days[0])] == approx([100] * 4)


def test_migration_adds_source_and_fetch_log(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    cols = {r[1] for r in db.execute("pragma table_info('corporate_actions')").fetchall()}
    assert "source" in cols
    db.execute("insert into fetch_log values ('nse_corporate_actions', '2026-01')")


def test_saved_nse_actions_carry_their_source(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    rows = json.loads(FIXTURE.read_text())
    ca.save(db, [a for a in map(ca.from_nse, rows) if a])
    assert db.execute("select distinct source from corporate_actions").fetchall() == [("nse",)]


# --- backfill -------------------------------------------------------------------------------------------

class FakeNse:
    def __init__(self, fail_on=None):
        self.paths, self.fail_on = [], fail_on

    def __call__(self, path):
        self.paths.append(path)
        if self.fail_on and self.fail_on in path:
            raise RuntimeError("blocked")
        return json.loads(FIXTURE.read_text())


def test_backfill_asks_one_calendar_month_at_a_time_in_nse_date_format(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    fake = FakeNse()
    ca.backfill(db, fake, since=date(2026, 1, 15), today=date(2026, 4, 10))
    assert fake.paths == [
        "/api/corporates-corporateActions?index=equities&from_date=01-01-2026&to_date=31-01-2026",
        "/api/corporates-corporateActions?index=equities&from_date=01-02-2026&to_date=28-02-2026",
        "/api/corporates-corporateActions?index=equities&from_date=01-03-2026&to_date=31-03-2026",
        "/api/corporates-corporateActions?index=equities&from_date=01-04-2026&to_date=30-04-2026",
    ]
    assert db.execute("select count(*) from corporate_actions").fetchone()[0] == 2   # split + bonus, deduped


def test_backfill_is_idempotent_and_skips_finished_months_but_not_the_current_one(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    ca.backfill(db, FakeNse(), since=date(2026, 1, 1), today=date(2026, 3, 10))
    again = FakeNse()
    ca.backfill(db, again, since=date(2026, 1, 1), today=date(2026, 3, 10))
    assert [p[-10:] for p in again.paths] == ["31-03-2026"]          # March is still running: fetched again
    assert db.execute("select count(*) from corporate_actions").fetchone()[0] == 2
    assert db.execute("select period from fetch_log order by period").fetchall() == [("2026-01",), ("2026-02",)]


def test_backfill_resumes_after_a_failed_month(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    with pytest.raises(RuntimeError):
        ca.backfill(db, FakeNse(fail_on="from_date=01-03-2026"), since=date(2026, 1, 1), today=date(2026, 6, 1))
    assert db.execute("select period from fetch_log order by period").fetchall() == [("2026-01",), ("2026-02",)]
    resume = FakeNse()
    ca.backfill(db, resume, since=date(2026, 1, 1), today=date(2026, 6, 1))
    assert resume.paths[0].endswith("from_date=01-03-2026&to_date=31-03-2026") and len(resume.paths) == 4


# --- yfinance fallback ----------------------------------------------------------------------------------

def jumpy_market(db):
    days = weekdays(date(2026, 1, 5), 30)
    load(db, "REALSPLIT", days, [500] * 15 + [100] * 15)              # 1:5 on days[15]
    load(db, "WRONGDAY", days, [500] * 15 + [100] * 15)
    load(db, "THIN", days, [500] * 15 + [100] * 15, value=1e6)        # 0.1 cr a day: under the floor
    load(db, "CRASH", days, [500] * 15 + [100] * 15)
    return days


def test_fallback_stores_only_date_matched_splits_for_liquid_unexplained_jumps(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    days = jumpy_market(db)
    asked = []
    splits = {"REALSPLIT": [(days[16], 5.0)],                        # one trading day off: accepted
              "WRONGDAY": [(days[25], 5.0)],                         # nowhere near the jump
              "THIN": [(days[15], 5.0)],
              "CRASH": []}

    def fetch(symbol):
        asked.append(symbol)
        return splits[symbol]
    n = ca.fallback_yfinance(db, fetch, floor_cr=1.0, since=date(2026, 1, 1))
    assert n == 1 and sorted(asked) == ["CRASH", "REALSPLIT", "WRONGDAY"]          # THIN is never asked
    assert db.execute("select symbol, ex_date, kind, numerator, denominator, source from corporate_actions"
                      ).fetchall() == [("REALSPLIT", days[16], "split", 5.0, 1.0, "yfinance")]
    assert sorted(s for s, _, _ in quality.big_moves(db)) == ["CRASH", "THIN", "WRONGDAY"]


def test_fallback_does_not_ask_about_a_jump_that_has_an_action(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    days = jumpy_market(db)
    action(db, "REALSPLIT", days[15], "split", 5, 1)
    asked = []
    ca.fallback_yfinance(db, lambda s: asked.append(s) or [], floor_cr=1.0, since=date(2026, 1, 1))
    assert "REALSPLIT" not in asked


# --- quality --------------------------------------------------------------------------------------------

def test_a_jump_with_an_action_within_two_trading_days_is_explained_and_counted_by_source(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    days = weekdays(date(2026, 1, 5), 30)
    load(db, "NSEHIT", days, [500] * 15 + [100] * 15)
    load(db, "YFHIT", days, [500] * 15 + [100] * 15)
    load(db, "NOPE", days, [500] * 15 + [100] * 15)
    action(db, "NSEHIT", days[15], "split", 5, 1, source="nse")
    action(db, "YFHIT", days[17], "split", 5, 1, source="yfinance")        # two trading days late, still explained
    assert [s for s, _, _ in quality.big_moves(db)] == ["NOPE"]
    assert quality.explained_jump_counts(db) == {"nse": 1, "yfinance": 1}
    text = quality.write_report(db, tmp_path / "q.md").read_text()
    assert "nse: 1" in text and "yfinance: 1" in text
