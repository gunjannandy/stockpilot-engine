"""TER and AUM for funds. The two AMFI files are saved as small fixtures in tests/fixtures/amfi/. Their column layout is the
one the parsers expect, built from AMFI's published description; the first real file must be checked against it (docs/status/D2.md)."""
from datetime import date
from pathlib import Path

import pytest

from stockpilot import store

from stockpilot.sources import fundcosts

from stockpilot.analysis import fundreview
from test_weekly import AS_OF, _fund, _hold, _peers

FIX = Path(__file__).parents[1] / "fixtures" / "amfi"


def test_ter_file_parses_regular_and_direct_and_skips_rows_without_a_number():
    got = fundcosts.parse_ter((FIX / "ter_sample.csv").read_bytes())
    assert got["fund 1"] == (1.85, 0.62)
    assert got["odd fund"] == (None, 0.55)
    assert "broken fund" not in got


def test_aum_file_converts_lakh_to_crore():
    got = fundcosts.parse_aum((FIX / "aum_sample.csv").read_bytes())
    assert got["fund 1"] == pytest.approx(12_500.005)      # Rs 1,250,000.50 lakh
    assert got["fund 2"] == 300
    assert "no number fund" not in got


def test_a_file_without_the_expected_columns_is_refused_loudly():
    with pytest.raises(fundcosts.FormatError):
        fundcosts.parse_aum(b"Name,Colour\nA,red\n")


def test_scheme_key_ignores_plan_and_option_words():
    assert fundcosts.scheme_key("Fund 1 - Direct Plan - Growth Option") == "fund 1"
    assert fundcosts.scheme_key("Fund 2 (IDCW)") == "fund 2"


def test_ingest_then_lookup_by_plan(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    n = fundcosts.ingest(db, date(2026, 10, 31), (FIX / "ter_sample.csv").read_bytes(), (FIX / "aum_sample.csv").read_bytes())
    assert n == 4 and fundcosts.ingest(db, date(2026, 10, 31), (FIX / "ter_sample.csv").read_bytes(), None) >= 1
    assert fundcosts.lookup(db, "Fund 1 - Direct Plan - Growth", "Direct Plan") == {"ter": 0.62, "aum_cr": pytest.approx(12_500.005)}
    assert fundcosts.lookup(db, "Fund 1 - Regular Plan - Growth", "Regular Plan")["ter"] == 1.85
    assert fundcosts.lookup(db, "Unknown", "Direct Plan") is None


def _costed(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    _peers(db)
    fundcosts.ingest(db, AS_OF, (FIX / "ter_sample.csv").read_bytes(), (FIX / "aum_sample.csv").read_bytes())
    return db


def test_review_shows_ter_and_flags_a_small_fund(tmp_path):
    db = _costed(tmp_path)
    _hold(db, "mf", "Fund 2", "INF2", 10)
    [row] = fundreview.review(db, AS_OF)
    assert row["ter"] == 0.95 and row["aum_cr"] == 300
    assert row["flags"] == ["small"] and "under ₹500 crore" in row["why"]


def test_review_does_not_flag_a_big_fund_and_works_without_cost_data(tmp_path):
    db = _costed(tmp_path)
    _hold(db, "mf", "Fund 1", "INF1", 10)
    _hold(db, "mf", "Fund 3", "INF3", 10)
    rows = {r["name"]: r for r in fundreview.review(db, AS_OF)}
    assert rows["Fund 1"]["flags"] == [] and rows["Fund 3"]["ter"] is None and rows["Fund 3"]["flags"] == []


def test_the_better_peer_named_is_never_a_small_fund(tmp_path):
    db = _costed(tmp_path)
    db.execute("update navs set nav = 400 where scheme_code = 5 and date = ?", [AS_OF])   # Fund 5 is best, AUM 450 cr
    _hold(db, "mf", "Fund 1", "INF1", 10)
    [row] = fundreview.review(db, AS_OF)
    assert row["verdict"] == "Review" and row["better_peer"] == "Fund 4"


def test_regular_plan_note_says_how_much_direct_saves(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    _peers(db)
    db.execute("update funds set plan = 'Regular Plan' where scheme_code = 1")
    fundcosts.ingest(db, AS_OF, (FIX / "ter_sample.csv").read_bytes(), None)
    _hold(db, "mf", "Fund 1", "INF1", 10)
    [row] = fundreview.review(db, AS_OF)
    assert "1.85%" in row["note"] and "0.62%" in row["note"]


def test_refresh_downloads_both_files_and_skips_quietly_when_no_url_is_set(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert fundcosts.refresh(db, date(2026, 11, 22), None, None, lambda u: pytest.fail("fetched")) == 0
    files = {"http://x/ter": (FIX / "ter_sample.csv").read_bytes(), "http://x/aum": (FIX / "aum_sample.csv").read_bytes()}
    assert fundcosts.refresh(db, date(2026, 11, 22), "http://x/ter", "http://x/aum", files.get) == 4
    assert fundcosts.lookup(db, "Fund 5", "Direct")["aum_cr"] == 450


def test_refresh_names_the_url_when_the_server_says_not_found(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    with pytest.raises(RuntimeError, match="http://x/ter"):
        fundcosts.refresh(db, date(2026, 11, 22), "http://x/ter", None, lambda u: None)
