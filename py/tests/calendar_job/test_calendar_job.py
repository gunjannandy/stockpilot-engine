import io
import sys
from datetime import date

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "runtime"))
from fake_runtime_worker import KEY, FakeRuntimeWorker  # noqa: E402

from stockpilot.io import Door  # noqa: E402
from stockpilot.jobs import calendar as cal  # noqa: E402
from stockpilot.runtime import run_job  # noqa: E402

HOLIDAYS = {"CM": [{"tradingDate": "25-Dec-2026", "description": "Christmas "}, {"tradingDate": "26-Jan-2027", "description": "Republic Day"}]}
ACTIONS = [
    {"symbol": "ABC", "isin": "INE000A01010", "exDate": "10-Dec-2026", "subject": "Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 2/- Per Share"},
    {"symbol": "DEF", "isin": "INE000B01010", "exDate": "11-Dec-2026", "subject": "Bonus 1:2"},
    {"symbol": "GHI", "exDate": "12-Dec-2026", "subject": "Dividend - Rs 5 Per Share"},
    {"symbol": "OLDCO", "exDate": "05-Dec-2026", "subject": "Change in Name and Symbol from OLDCO to NEWCO"},
    {"symbol": "GONE", "exDate": "20-Dec-2026", "subject": "Delisting of equity shares"},
]


def fetch(path):
    if "holiday-master" in path:
        return HOLIDAYS
    return ACTIONS if "index=equities" in path else []


def test_holidays_become_rows():
    rows = cal.holiday_rows(HOLIDAYS)
    assert [(r["kind"], r["date"], r["reason"]) for r in rows] == [("holiday", "2026-12-25", "Christmas"), ("holiday", "2027-01-26", "Republic Day")]


def test_actions_become_split_bonus_symbol_change_and_delisting_rows_and_nothing_else():
    rows = {r["kind"]: r for r in cal.action_rows(ACTIONS)}
    assert set(rows) == {"split", "bonus", "symbol_change", "delisting"}
    assert (rows["split"]["symbol"], rows["split"]["old_shares"], rows["split"]["new_shares"]) == ("ABC", 1, 5)
    assert (rows["bonus"]["symbol"], rows["bonus"]["old_shares"], rows["bonus"]["new_shares"]) == ("DEF", 2, 1)
    assert (rows["symbol_change"]["symbol"], rows["symbol_change"]["new_symbol"]) == ("OLDCO", "NEWCO")
    assert rows["delisting"]["symbol"] == "GONE"


def test_ids_are_stable_so_a_rerun_sends_the_same_rows():
    assert cal.action_rows(ACTIONS) == cal.action_rows(ACTIONS)
    assert len({r["id"] for r in cal.action_rows(ACTIONS)}) == 4


def test_the_job_publishes_the_calendar_dataset():
    w = FakeRuntimeWorker()
    run_job("calendar", lambda ctx: cal.run(ctx, fetch), door=Door("https://x.invalid", KEY, w.transport),
            subject="calendar", day="2026-11-27", out=io.StringIO())
    kinds = sorted(r["kind"] for r in w.rows["calendar"].values())
    assert kinds == ["bonus", "delisting", "holiday", "holiday", "split", "symbol_change"]


def test_one_corporate_action_feed_failing_does_not_hide_the_others_but_all_failing_fails_the_job():
    def sme_down(path):
        if "index=sme" in path:
            raise OSError("blocked")
        return fetch(path)

    assert len(cal.collect(date(2026, 11, 27), sme_down)) == 6

    def all_down(path):
        if "holiday-master" in path:
            return HOLIDAYS
        raise OSError("blocked")

    with pytest.raises(RuntimeError, match="every NSE corporate-action feed failed"):
        cal.collect(date(2026, 11, 27), all_down)
