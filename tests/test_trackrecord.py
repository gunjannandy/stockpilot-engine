"""T20: score every call at 1, 3 and 6 months, keep news buys apart, and let a separate reviewer propose at most three changes
that wait for the owner's Approve. The model is always a fake; the neutral people are "owner" and "father"."""
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from stockpilot import jobrun, review, trackrecord

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / "schemas" / "live-contract.json").read_text())
IST = timezone(timedelta(hours=5, minutes=30))
TODAY = date(2026, 11, 26)


def series(start: date, days: int, first: float, last: float) -> list[tuple[date, float]]:
    """A straight-line price path, one row per day."""
    return [(start + timedelta(d), first + (last - first) * d / days) for d in range(days + 1)]


def call(symbol="AAA", made_on=date(2026, 1, 5), **kw):
    base = {"symbol": symbol, "exchange": "NSE", "made_on": made_on, "route": "code", "call": "buy", "chance_3m": 70,
            "chance_6m": 65, "base_3m": 60, "base_6m": 60, "price": 100.0, "hurdle": 0.02, "model": "sonnet",
            "range_1m": {"low": 95.0, "high": 112.0}, "adjustments": [], "news_ids": []}
    return {**base, **kw}


def prices(**paths):
    """symbol -> rows. A stock that rose 10% over 91 days, another that fell, the Nifty up 2%."""
    return {s: rows for s, rows in paths.items()}


START = date(2026, 1, 5)
UP = series(START, 400, 100.0, 140.0)      # +10% by day 100
DOWN = series(START, 400, 100.0, 60.0)
NIFTY = series(START, 400, 1000.0, 1040.0)


# ---- scores reproduce on fixtures ------------------------------------------------------------------

def test_a_buy_that_beat_the_nifty_scores_a_hit_with_its_brier_and_the_base_rate_brier():
    rows = trackrecord.score_calls([call()], {"AAA": UP}, NIFTY, TODAY)
    r3 = next(r for r in rows if r["horizon"] == "3m")
    assert r3["hit"] == 1 and r3["excess"] == pytest.approx(0.0819, abs=1e-3)
    assert r3["brier"] == pytest.approx((0.70 - 1) ** 2)
    assert r3["base_brier"] == pytest.approx((0.60 - 1) ** 2)


def test_a_buy_that_fell_scores_a_miss_and_a_sell_that_fell_scores_a_hit():
    miss = trackrecord.score_calls([call("BBB")], {"BBB": DOWN}, NIFTY, TODAY)
    assert next(r for r in miss if r["horizon"] == "3m")["hit"] == 0
    sell = trackrecord.score_calls([call("BBB", call="sell", chance_3m=30, base_3m=40)], {"BBB": DOWN}, NIFTY, TODAY)
    r = next(r for r in sell if r["horizon"] == "3m")
    assert r["hit"] == 1 and r["brier"] == pytest.approx(0.30 ** 2)      # the chance is "beats the Nifty": it did not, 0.3 said so


def test_a_window_that_has_not_ended_is_not_scored_and_one_without_prices_is_skipped():
    young = call(made_on=TODAY - timedelta(days=40))
    rows = trackrecord.score_calls([young], {"AAA": series(TODAY - timedelta(40), 40, 100, 110)},
                                   series(TODAY - timedelta(40), 40, 1000, 1010), TODAY)
    assert [r["horizon"] for r in rows] == ["1m"]
    assert trackrecord.score_calls([call()], {}, NIFTY, TODAY) == []


def test_hold_and_wait_calls_give_a_brier_but_no_hit():
    rows = trackrecord.score_calls([call(call="hold")], {"AAA": UP}, NIFTY, TODAY)
    r3 = next(r for r in rows if r["horizon"] == "3m")
    assert r3["hit"] is None and r3["brier"] is not None


def test_one_month_is_judged_on_the_range_not_a_chance():
    inside = trackrecord.score_calls([call(range_1m={"low": 95, "high": 125})], {"AAA": UP}, NIFTY, TODAY)
    outside = trackrecord.score_calls([call(range_1m={"low": 90, "high": 101})], {"AAA": UP}, NIFTY, TODAY)
    one = lambda rows: next(r for r in rows if r["horizon"] == "1m")
    assert one(inside)["in_range"] is True and one(outside)["in_range"] is False
    assert one(inside)["brier"] is None


def test_scoring_is_the_same_every_time_it_runs():
    a = trackrecord.score_calls([call(), call("BBB")], {"AAA": UP, "BBB": DOWN}, NIFTY, TODAY)
    b = trackrecord.score_calls([call("BBB"), call()], {"BBB": DOWN, "AAA": UP}, NIFTY, TODAY)
    assert sorted(a, key=lambda r: (r["symbol"], r["horizon"])) == sorted(b, key=lambda r: (r["symbol"], r["horizon"]))


# ---- the summary ---------------------------------------------------------------------------------------

def many(n, route="code", hit=True, **kw):
    out = []
    for i in range(n):
        out.append(call(f"S{i}", made_on=START + timedelta(days=i % 5), route=route, **kw))
    return out, {f"S{i}": (UP if hit else DOWN) for i in range(n)}


def test_summary_gives_hit_rate_brier_and_calibration_per_horizon():
    cs, px = many(4)
    cs2, px2 = many(4, hit=False)
    cs2 = [{**c, "symbol": "X" + c["symbol"]} for c in cs2]
    px2 = {"X" + s: p for s, p in px2.items()}
    rows = trackrecord.score_calls(cs + cs2, {**px, **px2}, NIFTY, TODAY)
    s = trackrecord.summary(rows)
    three = s["code"]["3m"]
    assert three["n"] == 8 and three["hit_rate"] == 0.5
    assert three["brier"] == pytest.approx((4 * 0.09 + 4 * 0.49) / 8)
    assert three["base_brier"] == pytest.approx((4 * 0.16 + 4 * 0.36) / 8)
    assert three["calibration"] == [{"said": 0.7, "happened": 0.5, "n": 8}]
    assert s["code"]["1m"]["range_coverage"] is not None


def test_the_same_stock_called_twice_in_one_day_counts_once():
    c = call()
    rows = trackrecord.score_calls([c, {**c, "chance_3m": 20}], {"AAA": UP}, NIFTY, TODAY)
    assert len([r for r in rows if r["horizon"] == "3m"]) == 1
    assert next(r for r in rows if r["horizon"] == "3m")["brier"] == pytest.approx(0.64)      # the later call (20%) stands


def test_news_buys_are_scored_apart_and_linked_to_their_news():
    code = call("AAA")
    news = call("NNN", route="news", news_ids=["n1", "n2"], call="buy", chance_3m=55)
    rows = trackrecord.score_calls([code, news], {"AAA": UP, "NNN": UP}, NIFTY, TODAY)
    s = trackrecord.summary(rows)
    assert s["code"]["3m"]["n"] == 1 and s["news"]["3m"]["n"] == 1
    buys = trackrecord.news_buys(rows, {"n1": {"title": "Order win", "link": "https://example.com/a"}})
    assert buys == [{"symbol": "NNN", "exchange": "NSE", "made_on": "2026-01-05",
                     "news": [{"id": "n1", "title": "Order win", "link": "https://example.com/a"}, {"id": "n2", "title": None, "link": None}],
                     "results": {"1m": rows_hit(rows, "NNN", "1m"), "3m": 1, "6m": 1}}]


def rows_hit(rows, symbol, horizon):
    return next(r for r in rows if r["symbol"] == symbol and r["horizon"] == horizon)["hit"]


def test_a_small_record_says_it_is_too_early():
    cs, px = many(3)
    s = trackrecord.summary(trackrecord.score_calls(cs, px, NIFTY, TODAY))
    assert s["code"]["3m"]["verdict"] == "too early"
    assert "3 " in s["code"]["3m"]["line"] and "too early" in s["code"]["3m"]["line"]


# ---- the weekly review -----------------------------------------------------------------------------

def adj(area, points, horizon="m3"):
    return {"area": area, "from_evidence": "e1", "points": points, "horizon": horizon}


def scored_world(n=40):
    """n calls a month apart over three years: news adjustments always hurt (they push up, stock falls)."""
    cs, px = [], {}
    for i in range(n):
        sym = f"R{i}"
        made = date(2023, 1, 2) + timedelta(days=20 * i)
        fell = i % 2 == 0
        cs.append(call(sym, made_on=made, chance_3m=62, base_3m=55, adjustments=[adj("news", 5)]))
        px[sym] = series(made, 200, 100.0, 70.0 if fell else 130.0)
    nifty = series(date(2023, 1, 2), 1200, 1000.0, 1100.0)
    return cs, px, nifty


class Reviewer:
    def __init__(self, proposals):
        self.proposals, self.prompts = proposals, []

    def ask(self, prompt):
        self.prompts.append(prompt)
        return json.dumps({"proposals": self.proposals})


def lower_news_cap(**kw):
    p = {"kind": "lower_cap", "target": "news", "change": "Lower the news adjustment limit from 5 to 3 points.",
         "new_value": 3, "why": "News pushed chances up and the stocks fell more often than not.",
         "evidence": {"area": "news", "n": 40}}
    return {**p, **kw}


def dossier(**kw):
    cs, px, nifty = scored_world()
    rows = trackrecord.score_calls(cs, px, nifty, date(2026, 11, 26))
    return review.dossier(cs, rows, date(2026, 11, 26), **kw)


def test_the_dossier_holds_the_scored_calls_by_area_and_leaves_out_the_newest_three_months():
    d = dossier()
    news = d["areas"]["news"]
    assert news["n"] > 0 and news["avg_points"] == 5
    assert d["holdout_from"] == "2026-08-28"
    assert all(c["made_on"] < d["holdout_from"] for c in d["calls"])


def test_a_proposal_names_its_evidence_and_waits():
    d = dossier()
    n = d["areas"]["news"]["n"]
    got = review.propose(d, Reviewer([lower_news_cap(evidence={"area": "news", "n": n})]))
    assert len(got["proposals"]) == 1 and got["dropped"] == []
    assert got["proposals"][0]["status"] == "proposed"


def test_at_most_three_proposals_are_kept_and_the_rest_are_said_to_be_dropped():
    d = dossier()
    n = d["areas"]["news"]["n"]
    four = [lower_news_cap(evidence={"area": "news", "n": n}, target=a, new_value=1 + i) for i, a in
            enumerate(["news", "news", "news", "news"])]
    got = review.propose(d, Reviewer(four))
    assert len(got["proposals"]) == 3 and any("more than three" in x.lower() for x in got["dropped"])


def test_a_proposal_with_evidence_that_does_not_match_the_data_is_dropped():
    d = dossier()
    got = review.propose(d, Reviewer([lower_news_cap(evidence={"area": "news", "n": 999})]))
    assert got["proposals"] == [] and any("n" in x and "does not match" in x for x in got["dropped"])


def test_a_cap_may_only_go_down_and_an_unknown_area_is_dropped():
    d = dossier()
    n = d["areas"]["news"]["n"]
    got = review.propose(d, Reviewer([lower_news_cap(evidence={"area": "news", "n": n}, new_value=8),
                                      lower_news_cap(target="weather", evidence={"area": "weather", "n": n})]))
    assert got["proposals"] == [] and len(got["dropped"]) == 2


def test_a_prompt_line_about_money_or_numbers_is_dropped_like_a_house_rule():
    d = dossier()
    n = d["areas"]["news"]["n"]
    bad = {"kind": "prompt_line", "target": "forecast_form", "change": "Treat any stop loss above 5% as a sell.",
           "why": "x", "evidence": {"area": "news", "n": n}}
    good = {**bad, "change": "Say when a news item is a rumour, not a filing."}
    got = review.propose(d, Reviewer([bad, good]))
    assert [p["change"] for p in got["proposals"]] == [good["change"]]


def test_a_reviewer_that_answers_badly_gives_no_proposals_and_a_plain_reason():
    class Junk:
        def ask(self, prompt):
            return "not json"
    got = review.propose(dossier(), Junk())
    assert got["proposals"] == [] and "could not read" in got["dropped"][0].lower()


def test_proposals_become_asks_that_wait_for_approve_and_change_nothing():
    d = dossier()
    n = d["areas"]["news"]["n"]
    got = review.propose(d, Reviewer([lower_news_cap(evidence={"area": "news", "n": n})]))
    now = datetime(2026, 11, 28, 6, 0, tzinfo=IST).isoformat()
    fb, asks = review.rows(got["proposals"], "review_2026-11-28", now)
    assert fb["person"] == "owner" and fb["status"] == "understood"
    assert [a["route"] for a in asks] == ["owner_approval"] and [a["status"] for a in asks] == ["waiting_for_approval"]
    assert asks[0]["tag"] == "forecast" and asks[0]["issue_number"] is None
    for table, row in (("feedback", fb), ("asks", asks[0])):
        assert jobrun.check_shape(row, CONTRACT["tables"][table]["columns"]) == []


def test_the_forecaster_never_sees_its_record():
    import re
    import stockpilot.forecast as fc
    import stockpilot.forecast_form as ff
    for mod in (ff, fc):
        src = Path(mod.__file__).read_text()
        assert not re.search(r"^\s*(from|import)\s+stockpilot(\.| import )\s*(trackrecord|review)\b", src, re.M), mod.__name__
        assert not re.search(r"from stockpilot import .*\b(trackrecord|review)\b", src), mod.__name__
    assert "brier" not in (ROOT / "prompts" / "forecast_form.md").read_text().lower()


def test_the_reviewer_prompt_is_not_the_forecast_prompt():
    assert (ROOT / "prompts" / "weekly_review.md").read_text() != (ROOT / "prompts" / "forecast_form.md").read_text()
    prompt = review.prompt(dossier())
    assert "scored" in prompt and "at most three" in prompt.lower()


# ---- the job ----------------------------------------------------------------------------------------------

def run_job(model, calls_px=None, saved=None):
    cs, px, nifty = calls_px or scored_world()
    sink = jobrun.MemorySink()
    r = jobrun.JobRunner(sink, model=model, clock=lambda: datetime(2026, 11, 28, 6, 0, tzinfo=IST))
    saved = [] if saved is None else saved
    r.register("weekly_review", review.handler(load=lambda: (cs, px, nifty, {}), save=lambda fb, asks, doc: saved.append((fb, asks, doc)),
                                                today=lambda: date(2026, 11, 26)))
    job_id = r.enqueue("weekly_review", {}, asked_by="system")
    r.run(job_id)
    return sink.jobs[job_id], sink.lines[job_id], saved


def test_the_job_says_how_many_proposals_wait_and_saves_them():
    d = dossier()
    n = d["areas"]["news"]["n"]
    job, lines, saved = run_job(Reviewer([lower_news_cap(evidence={"area": "news", "n": n})]))
    assert job["status"] == "done" and "1 proposal waiting for Approve" in job["result"]
    assert len(saved) == 1 and saved[0][1][0]["status"] == "waiting_for_approval"
    assert "track_record" in saved[0][2] and saved[0][2]["track_record"]["code"]["3m"]["n"] > 0


def test_with_no_scored_calls_the_job_spends_nothing():
    model = Reviewer([])
    job, _, saved = run_job(model, ([], {}, NIFTY))
    assert job["status"] == "done" and "Nothing to review yet" in job["result"]
    assert model.prompts == [] and saved[0][1] == []          # the record is still saved; no asks


def test_with_no_model_the_job_fails_in_plain_words():
    job, _, saved = run_job(None)
    assert job["status"] == "failed" and job["error"] == jobrun.NO_MODEL and saved == []
