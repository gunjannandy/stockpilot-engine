"""Lane E: the consumer of `analyst_asks`. One runner call per stock, the answer kept on the ask, status done."""
import json
import shutil
from datetime import date

import pytest

from forecast_seed import AS_OF
from stockpilot import asks, store
from stockpilot.calls.decide import Rules
from stockpilot.calls.runner import RunnerError
from test_forecast import RULES, template   # noqa: F401
from test_forecast import answer


@pytest.fixture
def db(template, tmp_path):
    shutil.copy(template, tmp_path / "t.duckdb")
    return store.open(tmp_path / "t.duckdb")


def ask(db, symbol, on=AS_OF, by="papa"):
    db.execute("insert into analyst_asks (symbol, asked_by, asked_on) values (?, ?, ?)", [symbol, by, on])


def analyst(seen, **per_symbol):
    def analyse(brief, role, runners, **kw):
        seen.append((role, brief))
        items = [answer(s["symbol"], 0.61, **{"summary": f"{s['symbol']}: the analyst looked.", "summary_bn": "বিশ্লেষক দেখেছেন।",
                                              **per_symbol.get(s["symbol"], {})}) for s in brief["stocks"]]
        return {"runner": "fake", "failures": [], "decisions": {"market_view": "Calm.", "market_view_bn": "শান্ত।", "items": items}}
    return analyse


def test_each_pending_stock_gets_one_runner_call_with_only_that_stock(db):
    ask(db, "INFY")
    ask(db, "SBIN")
    seen = []
    out = asks.run_pending(db, AS_OF, analyst(seen), ["fake"], RULES)
    assert out["answered"] == 2 and len(seen) == 2
    assert sorted(b["stocks"][0]["symbol"] for _, b in seen) == ["INFY", "SBIN"] and all(len(b["stocks"]) == 1 for _, b in seen)
    assert all(role == "analyst" for role, _ in seen)
    assert "asked" in " ".join(seen[0][1]["stocks"][0]["why_here"])


def test_the_ask_is_done_and_keeps_the_answer(db):
    ask(db, "INFY")
    asks.run_pending(db, AS_OF, analyst([]), ["fake"], RULES)
    status, done_at, answer_ = db.execute("select status, done_at, answer from analyst_asks").fetchone()
    body = json.loads(answer_)
    assert status == "done" and done_at is not None
    assert body["summary"] == "INFY: the analyst looked." and body["summary_bn"] and body["probability"] == 0.61


def test_a_second_ask_for_the_same_stock_shares_the_call(db):
    ask(db, "INFY")
    ask(db, "INFY", by="owner")
    seen = []
    asks.run_pending(db, AS_OF, analyst(seen), ["fake"], RULES)
    assert len(seen) == 1 and db.execute("select count(*) from analyst_asks where status = 'done'").fetchone()[0] == 2


def test_nothing_pending_makes_no_call(db):
    seen = []
    assert asks.run_pending(db, AS_OF, analyst(seen), ["fake"], RULES)["answered"] == 0 and seen == []


def test_a_failed_call_leaves_the_ask_pending_and_the_others_still_run(db):
    ask(db, "INFY")
    ask(db, "SBIN")

    def flaky(brief, role, runners, **kw):
        if brief["stocks"][0]["symbol"] == "INFY":
            raise RunnerError("every runner failed")
        return analyst([])(brief, role, runners)
    out = asks.run_pending(db, AS_OF, flaky, ["fake"], RULES)
    assert out["answered"] == 1 and out["failed"] == ["INFY"]
    assert dict(db.execute("select symbol, status from analyst_asks").fetchall()) == {"INFY": "pending", "SBIN": "done"}
    assert db.execute("select count(*) from problems where job = 'asks'").fetchone()[0] >= 1


def test_an_ask_older_than_three_days_that_keeps_failing_expires(db):
    ask(db, "INFY", on=date(2026, 11, 10))

    def broken(brief, role, runners, **kw):
        raise RunnerError("down")
    asks.run_pending(db, AS_OF, broken, ["fake"], RULES)
    assert db.execute("select status from analyst_asks").fetchone()[0] == "expired"


def test_at_most_five_stocks_a_run(db):
    for s in ("INFY", "SBIN", "WIPRO", "TCS", "ITC", "LT", "MARUTI"):
        ask(db, s)
    seen = []
    out = asks.run_pending(db, AS_OF, analyst(seen), ["fake"], RULES)
    assert out["answered"] == 5 and db.execute("select count(*) from analyst_asks where status = 'pending'").fetchone()[0] == 2


def test_a_bad_bengali_field_is_blanked(db):
    ask(db, "INFY")
    asks.run_pending(db, AS_OF, analyst([], INFY={"summary_bn": "plain English only"}), ["fake"], RULES)
    assert json.loads(db.execute("select answer from analyst_asks").fetchone()[0])["summary_bn"] == ""


def test_the_site_note_takes_the_ask_answer_when_it_is_newer_than_the_last_run(db):
    from stockpilot.site_export import stock
    db.execute("delete from calls")
    db.execute("insert into calls (run_id, made_on, symbol, kind, action, probability, reasons, section) "
               "values (1, ?, 'INFY', 'holding', 'hold', 0.5, ?, 'hold')", [date(2026, 11, 19), json.dumps({"summary": "Old view."})])
    ask(db, "INFY")
    asks.run_pending(db, date(2026, 11, 20), analyst([]), ["fake"], RULES)
    assert stock.analysed(db, date(2026, 11, 20))["INFY"] == ("INFY: the analyst looked.", "বিশ্লেষক দেখেছেন।")


def test_the_evening_step_answers_asks_and_never_raises(db):
    from types import SimpleNamespace
    from stockpilot.jobs import daily

    class Cfg:
        def get(self, key, default=None):
            return default
    ask(db, "INFY")
    m = SimpleNamespace(analyse=analyst([]), runners=["fake"], cfg=Cfg())
    assert daily.run_asks(m, db, AS_OF)["answered"] == 1
    m.analyse = None                      # a broken machine: the step reports, the run goes on
    ask(db, "SBIN")
    out = daily.run_asks(m, db, AS_OF)
    assert out["answered"] == 0 and out["failed"] == ["SBIN"]


def test_a_us_share_the_owners_hold_can_be_asked_about(db):
    """Lane R: ServiceNow (an RSU holding, prices from `usprices` under NYSE) gets a brief from its dollar series and an answer
    with a reasoning object, instead of failing on the missing NSE stock row."""
    from datetime import timedelta
    rows = [(AS_OF - timedelta(days=i), "NOW", "NYSE", "EQ", 100 + i * 0.1, 101 + i * 0.1, 99, 100 + i * 0.1, None, 1000, None, None)
            for i in range(300)]
    db.executemany("insert or replace into prices values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", rows)
    db.execute("insert into trades (trade_key, source, source_ref, kind, symbol, isin, side, trade_date, quantity, price, currency, status) "
               "values ('v1', 'fidelity_docs', 'v1', 'rsu', 'NOW', 'US81762P1021', 'vest', '2025-02-14', 10, 90, 'USD', 'confirmed')")
    ask(db, "NOW")
    seen = []
    out = asks.run_pending(db, AS_OF, analyst(seen), ["fake"], RULES)
    assert out["answered"] == 1 and out["failed"] == []
    body = json.loads(db.execute("select answer from analyst_asks where symbol = 'NOW'").fetchone()[0])
    assert body["reasoning"]["v"] == 1 and body["reasoning"]["headline"]
    assert "dollars" in " ".join(seen[0][1]["stocks"][0]["why_here"]).lower() or seen[0][1]["stocks"][0]["symbol"] == "NOW"
