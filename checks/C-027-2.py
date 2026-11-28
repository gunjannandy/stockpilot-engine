"""C-027-1 (data half): market health from fixtures: the Nifty's trend, breadth and the value band, every sentence in Bengali."""
import json
import re
from datetime import date

from stockpilot.jobs.market import breadth, row, trend, value_band
from stockpilot.jobs.market import templates as T


def rising(n=250, start=100.0, step=0.5):
    return [start + step * i for i in range(n)]


def test_nifty_trend_against_its_200_day_average():
    close, pct, d = trend(rising())
    assert d == "up" and pct > 0 and close == rising()[-1]
    assert trend(list(reversed(rising())))[2] == "down"
    assert trend(rising(100)) == (None, None, None)       # under 200 days: nothing is guessed


def test_breadth_counts_stocks_above_their_average_and_needs_enough_of_them():
    series = {f"U{i}": rising() for i in range(80)} | {f"D{i}": list(reversed(rising())) for i in range(40)}
    assert breadth(series) == (66.7, 120)
    assert breadth({"A": rising()}) == (None, 1)


def test_value_band_from_the_middle_pe():
    assert value_band([12.0] * 120) == (12.0, "cheap")
    assert value_band([21.0] * 120) == (21.0, "fair")
    assert value_band([40.0] * 120) == (40.0, "dear")
    assert value_band([-5.0, 0] * 100) == (None, None)    # loss makers are not a P/E
    assert value_band([20.0] * 10) == (None, None)


def test_the_row_carries_sentences_in_both_languages():
    series = {f"U{i}": rising() for i in range(120)}
    r = row(date(2026, 11, 28), rising(), series, [20.0] * 120)
    assert (r["nifty_trend"], r["breadth_pct"], r["value_band"]) == ("up", 100.0, "fair")
    s = json.loads(r["sentences_json"])
    assert [x["key"] for x in s] == ["trend_up", "breadth", "value_fair"]
    assert all(re.search("[ঀ-৿]", x["bn"]) for x in s)


def test_every_template_has_bengali_with_the_same_placeholders():
    for key, t in T.TEMPLATES.items():
        assert re.search("[ঀ-৿]", t["bn"]), key
        assert T.fields(t["en"]) == T.fields(t["bn"]), key
