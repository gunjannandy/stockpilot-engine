"""Lane R10: thesis-break sells, 8 quarters in the dossier (split-adjusted EPS), headlines problems by cause, a wider
results calendar."""
import shutil
import urllib.error
from datetime import date, datetime, timedelta

import pytest

from forecast_seed import AS_OF, SECTOR_INDEX, seeded
from stockpilot import dossier, forecast, readiness, store
from stockpilot.book import positions
from stockpilot.calls.decide import Rules
from stockpilot.sources import events, headlines
from test_decide import PV, item, lot, run, by

RULES = Rules(sector_index=SECTOR_INDEX)


# ---- 1. thesis breaks are facts for the analyst (lane E: they no longer sell by themselves; see tests/calls/test_sell_rules.py)

# ---- 1. thesis-break sells: the checks ---------------------------------------------------------------------

@pytest.fixture(scope="module")
def template(tmp_path_factory):
    folder = tmp_path_factory.mktemp("seed")
    d = seeded(folder)
    d.execute("delete from calls where symbol = 'INFY'")
    d.execute("checkpoint")
    d.close()
    return folder / "sp.duckdb"


@pytest.fixture
def db(template, tmp_path):
    shutil.copy(template, tmp_path / "t.duckdb")
    return store.open(tmp_path / "t.duckdb")


def quarter(db, symbol, period_end, net_profit, eps=1.0, revenue=1000.0, filed_at=None, consolidated=True):
    filed = filed_at or datetime.combine(period_end + timedelta(days=45), datetime.min.time())
    db.execute("insert into quarterly values (null, ?, ?, ?, ?, ?, null, ?, ?, 'u')",
               [symbol, period_end, consolidated, filed, revenue, net_profit, eps])


def checks(db, rules=RULES, day=AS_OF):
    held = positions.held(db, day)
    pv = sum(p.value for p in held if p.kind == "equity")
    ctx = dossier.context(db, day, None, held, rules.sector_index)
    return forecast.holding_checks(db, day, held, rules, pv, ctx.sector_returns)


def test_a_latest_quarter_profit_down_25_percent_on_a_year_ago_is_a_thesis_break(db):
    quarter(db, "ITC", date(2025, 9, 30), 100.0)
    quarter(db, "ITC", date(2026, 9, 30), 75.0)
    found = checks(db)["ITC"]
    assert any("profit" in t and "25%" in t for t in found["thesis_break"])
    assert any("profit" in t for t in found["triggers"])           # it also puts the holding in front of the model


def test_a_profit_fall_under_25_percent_is_not_a_break(db):
    quarter(db, "ITC", date(2025, 9, 30), 100.0)
    quarter(db, "ITC", date(2026, 9, 30), 76.0)
    assert "ITC" not in checks(db) or not checks(db)["ITC"]["thesis_break"]


def test_a_swing_to_a_loss_is_a_break_and_a_loss_a_year_ago_is_not(db):
    quarter(db, "ITC", date(2025, 9, 30), 100.0)
    quarter(db, "ITC", date(2026, 9, 30), -10.0)
    assert checks(db)["ITC"]["thesis_break"]
    quarter(db, "TCS", date(2025, 9, 30), -50.0)
    quarter(db, "TCS", date(2026, 9, 30), -100.0)
    assert "TCS" not in checks(db) or not checks(db)["TCS"]["thesis_break"]


def test_the_quarter_compared_is_the_same_one_a_year_earlier_not_the_one_before(db):
    quarter(db, "ITC", date(2025, 9, 30), 100.0)
    quarter(db, "ITC", date(2026, 6, 30), 400.0)
    quarter(db, "ITC", date(2026, 9, 30), 110.0)         # up on Sept 2025, though far below June
    assert "ITC" not in checks(db) or not checks(db)["ITC"]["thesis_break"]


def test_a_quarter_filed_after_today_is_not_known_yet(db):
    quarter(db, "ITC", date(2025, 9, 30), 100.0)
    quarter(db, "ITC", date(2026, 9, 30), 10.0, filed_at=datetime.combine(AS_OF + timedelta(days=3), datetime.min.time()))
    assert "ITC" not in checks(db) or not checks(db)["ITC"]["thesis_break"]


def test_asm_gsm_is_a_thesis_break(db):
    db.execute("insert into surveillance values (?, 'ITC', 'ASM Stage I')", [AS_OF])
    assert any("ASM Stage I" in t for t in checks(db)["ITC"]["thesis_break"])


def test_twenty_points_behind_the_sector_is_a_thesis_break(db):
    for n, d in enumerate(db.execute("select date from prices where symbol = 'TATAMOTORS' order by date desc limit 64").fetchall()):
        db.execute("update prices set close = close * ? where symbol = 'TATAMOTORS' and date = ?", [0.7 if n == 0 else 1.0, d[0]])
    assert any("behind its sector" in t for t in checks(db)["TATAMOTORS"]["thesis_break"])


def test_a_lot_turning_long_term_or_a_big_weight_is_a_check_but_not_a_thesis_break(db):
    assert not checks(db)["WIPRO"]["thesis_break"]


def test_the_threshold_comes_from_config():
    assert Rules().results_miss == 0.25
    assert Rules.from_config({"rules": {"results_miss": 0.4}}).results_miss == 0.4


def test_the_evening_no_longer_sells_on_one_weak_quarter_but_tells_the_analyst(db):
    quarter(db, "ITC", date(2025, 9, 30), 100.0)
    quarter(db, "ITC", date(2026, 9, 30), 50.0)
    from test_forecast import fake_analyse, go, rows
    seen = []
    go(db, fake_analyse(default=0.50, seen=seen))
    import json
    kind = json.loads(db.execute("select reasons from calls where symbol = 'ITC' and made_on = ?", [AS_OF]).fetchone()[0]).get("sell_kind")
    assert kind != "sell"            # this database's own scored calls may pull 50% down to Weak, never to Sell
    stocks = {s["symbol"]: s for _, b in seen for s in b["stocks"]}
    assert any("profit" in w for w in stocks["ITC"]["why_here"])


# ---- 2. eight quarters in the dossier ----------------------------------------------------------------------

def test_the_dossier_has_eight_quarters_with_growth_and_a_blank_when_unfiled(db):
    for i in range(10):
        end = date(2024, 6, 30) + timedelta(days=91 * i)
        quarter(db, "INFY", end, 1e9 + 1e7 * i, eps=10.0 + i, revenue=1e10 + 1e8 * i)
    d = dossier.build(db, "INFY", AS_OF)
    q = d["quarters"]
    assert len(q["rows"]) == 8
    assert q["rows"][0]["revenue"] > q["rows"][-1]["revenue"]            # newest first
    assert set(q["rows"][0]) == {"period", "revenue", "net_profit", "eps"}
    assert q["yoy"]["net_profit"] is not None and q["yoy"]["revenue"] is not None


def test_no_quarters_means_no_block(db):
    assert "quarters" not in dossier.build(db, "INFY", AS_OF)


def test_the_quarterly_table_missing_leaves_the_block_out(db):
    db.execute("drop table quarterly")
    assert "quarters" not in dossier.build(db, "INFY", AS_OF)


def action(db, ex, kind, n, d):
    db.execute("insert into corporate_actions (symbol, ex_date, kind, numerator, denominator) values ('INFY', ?, ?, ?, ?)",
               [ex, kind, n, d])


def test_eps_filed_before_a_bonus_is_divided_by_it(db):
    # HDFC Bank's 1:1 bonus: quarters filed before it are on half the shares, so their EPS is divided by 2
    action(db, date(2026, 4, 1), "bonus", 1, 1)
    quarter(db, "INFY", date(2025, 12, 31), 100.0, eps=24.0, filed_at=datetime(2026, 1, 20))
    quarter(db, "INFY", date(2026, 6, 30), 100.0, eps=13.0, filed_at=datetime(2026, 8, 1))      # filed after: as filed
    rows = {r["period"]: r for r in dossier.build(db, "INFY", AS_OF)["quarters"]["rows"]}
    assert rows["2025-12-31"]["eps"] == 12.0 and rows["2026-06-30"]["eps"] == 13.0


def test_a_split_and_a_bonus_multiply(db):
    action(db, date(2026, 2, 1), "split", 5, 1)
    action(db, date(2026, 5, 1), "bonus", 1, 1)
    quarter(db, "INFY", date(2025, 12, 31), 100.0, eps=100.0, filed_at=datetime(2026, 1, 15))   # both came after: 100 / (5 * 2)
    quarter(db, "INFY", date(2026, 3, 31), 100.0, eps=20.0, filed_at=datetime(2026, 4, 20))     # only the bonus: 20 / 2
    rows = {r["period"]: r["eps"] for r in dossier.build(db, "INFY", AS_OF)["quarters"]["rows"]}
    assert rows == {"2025-12-31": 10.0, "2026-03-31": 10.0}


def test_an_action_not_yet_in_effect_changes_nothing(db):
    action(db, AS_OF + timedelta(days=10), "bonus", 1, 1)
    quarter(db, "INFY", date(2026, 6, 30), 100.0, eps=13.0, filed_at=datetime(2026, 8, 1))
    assert dossier.build(db, "INFY", AS_OF)["quarters"]["rows"][0]["eps"] == 13.0


def test_other_kinds_of_action_are_ignored(db):
    action(db, date(2026, 9, 1), "dividend", 5, 1)
    quarter(db, "INFY", date(2026, 3, 31), 100.0, eps=13.0, filed_at=datetime(2026, 5, 1))
    assert dossier.build(db, "INFY", AS_OF)["quarters"]["rows"][0]["eps"] == 13.0


def test_growth_on_a_year_ago_uses_adjusted_eps(db):
    action(db, date(2026, 1, 1), "bonus", 1, 1)
    quarter(db, "INFY", date(2025, 9, 30), 100.0, eps=24.0, filed_at=datetime(2025, 10, 20))    # 12 on today's shares
    quarter(db, "INFY", date(2026, 9, 30), 120.0, eps=13.2, filed_at=datetime(2026, 10, 20))
    yoy = dossier.build(db, "INFY", AS_OF)["quarters"]["yoy"]
    assert yoy["eps"] == 0.1 and yoy["net_profit"] == 0.2


def test_the_dossier_stays_small_with_quarters(db):
    import json
    for i in range(8):
        quarter(db, "INFY", date(2024, 12, 31) + timedelta(days=91 * i), 1e10 + i, eps=10.0 + i, revenue=1e11)
    assert len(json.dumps(dossier.build(db, "INFY", AS_OF), default=str, separators=(",", ":"))) / 4 < 1100


# ---- 3. headlines problems by cause ------------------------------------------------------------------------

NAMES = {f"S{i}": f"Company {i}" for i in range(6)}


def problems(db):
    return db.execute("select key, message, severity from problems where job = 'daily_decide' and key like 'headlines%' "
                      "order by id").fetchall()


def test_thirty_five_failing_feeds_are_one_problem(db):
    names = {f"S{i}": f"Company {i}" for i in range(35)}

    def fetch(url):
        raise urllib.error.URLError("timed out")
    headlines.for_symbols(db, AS_OF, list(names), names, fetch)
    [(key, message, _)] = problems(db)
    assert key == "headlines" and "Google News failed for 35 stocks" in message


def test_one_stock_reads_as_one_stock(db):
    def fetch(url):
        raise OSError("boom")
    headlines.for_symbols(db, AS_OF, ["S0"], NAMES, fetch)
    assert "Google News failed for 1 stock" in problems(db)[0][1] and "stocks" not in problems(db)[0][1]


def test_no_failure_means_no_problem(db):
    headlines.for_symbols(db, AS_OF, ["S0", "S1"], NAMES, lambda url: b"<rss><channel></channel></rss>")
    assert problems(db) == []


def test_a_failed_stock_is_not_marked_fetched_and_is_retried(db):
    calls = []

    def fetch(url):
        calls.append(url)
        raise OSError("down")
    headlines.for_symbols(db, AS_OF, ["S0"], NAMES, fetch)
    headlines.for_symbols(db, AS_OF, ["S0"], NAMES, fetch)
    assert len(calls) == 2


def test_different_causes_are_different_problems(db):
    def fetch(url):
        raise (OSError("down") if "Company 0" in url or "Company%200" in url else ValueError("bad feed"))
    headlines.for_symbols(db, AS_OF, ["S0", "S1", "S2"], NAMES, fetch)
    rows = problems(db)
    assert len(rows) == 2 and all(k.startswith("headlines") for k, _, _ in rows)
    assert any("failed for 1 stock" in m for _, m, _ in rows) and any("failed for 2 stocks" in m for _, m, _ in rows)


# ---- 4. results dates --------------------------------------------------------------------------------------

DAY = date(2026, 11, 20)
ROW = {"symbol": "ACME", "purpose": "Financial Results", "bm_desc": "x", "date": "30-Dec-2026"}


def test_the_calendar_asks_for_the_next_sixty_days_first(db):
    paths = []

    def fetch_json(path):
        paths.append(path)
        return [ROW]
    assert events.ingest(db, DAY, fetch_json) == 1
    assert paths == ["/api/event-calendar?index=equities&from_date=20-11-2026&to_date=19-01-2027"]


def test_a_failed_wide_request_falls_back_to_the_short_list(db):
    paths = []

    def fetch_json(path):
        paths.append(path)
        if "from_date" in path:
            raise RuntimeError("403")
        return [ROW]
    assert events.ingest(db, DAY, fetch_json) == 1
    assert paths[-1] == "/api/event-calendar?index=equities"


def test_an_empty_wide_answer_falls_back_too(db):
    assert events.ingest(db, DAY, lambda p: [] if "from_date" in p else [ROW]) == 1


def test_readiness_says_how_far_the_results_dates_reach(db):
    db.execute("delete from results_calendar")
    db.execute("insert into results_calendar values ('X', ?, 'Financial Results', 'q')", [AS_OF + timedelta(days=5)])
    gap = [g for g in readiness.check(db, AS_OF)["gaps"] if "Results dates" in g]
    assert gap and str(AS_OF + timedelta(days=5)) in gap[0]
    db.execute("insert into results_calendar values ('Y', ?, 'Financial Results', 'q')", [AS_OF + timedelta(days=50)])
    assert not [g for g in readiness.check(db, AS_OF)["gaps"] if "Results dates" in g]


def test_an_empty_calendar_is_a_gap_and_a_missing_table_is_not_an_error(db):
    db.execute("delete from results_calendar")
    assert [g for g in readiness.check(db, AS_OF)["gaps"] if "Results dates" in g]
    db.execute("drop table results_calendar")
    readiness.check(db, AS_OF)
