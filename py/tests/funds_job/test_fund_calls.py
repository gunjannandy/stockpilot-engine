import json
from datetime import date, timedelta

from stockpilot.jobs.funds import calls

END = date(2026, 11, 27)


def navs(yearly: float, weeks: int = 5 * 52) -> str:
    return json.dumps([[(END - timedelta(weeks=weeks - i)).isoformat(), round(10 * (1 + yearly) ** (i / 52), 4)]
                       for i in range(weeks + 1)])


def row(i: int, yearly: float, **over) -> dict:
    r = {"id": f"f{i}", "name": f"Fund {i}", "category": "Equity Scheme - Flexi Cap Fund", "r1": yearly * 100,
         "r3": yearly * 100, "cat_r1": 10.0, "roll_loss_share": 0.0, "aum_cr": 5000.0, "ter": 0.5,
         "navs_json": navs(yearly)}
    r.update(over)
    return r


def universe() -> list[dict]:
    return [row(i, 0.04 + 0.02 * i) for i in range(12)]


def test_top_quarter_with_clean_record_is_buy_and_top_half_with_a_gap_is_watch():
    rows = universe()
    rows[11]["aum_cr"] = 50.0                      # best return but small: only a watch
    by = {s["row"]["id"]: s for s in calls.screen(rows)}
    assert by["f11"]["call"] == "watch" and "size is small or unknown" in by["f11"]["reasons"]
    assert by["f10"]["call"] == "buy" and by["f9"]["call"] == "buy"
    assert by["f7"]["call"] == "watch" and "f3" not in by


def test_small_category_gets_no_calls():
    assert calls.screen(universe()[:4]) == []


def test_rate_is_given_only_with_enough_cases():
    out = calls.build(universe(), "2026-11-27")
    c = {r["id"]: r for r in out}
    assert c["f10"]["kind"] == "call" and c["f10"]["chance"] is None and c["f10"]["cases"] is None
    assert all(r["caveat"] for r in out)
    track = [r for r in out if r["kind"] == "track"]
    assert track and all(t["call"] is None for t in track)


def test_steady_leaders_keep_winning_in_the_track_record():
    rates = calls.base_rates(universe())
    top = rates[("Equity Scheme", 1)]
    assert top["hit_rate"] == 1.0 and top["periods"] >= 2
    assert rates[("Equity Scheme", 4)]["hit_rate"] == 0.0
