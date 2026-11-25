"""Lane B step 4: the nightly check. Units explained by lots against Kite's; every difference is named, opens a problem and
(through the doctor) one GitHub issue. A mismatch is a bug, never a normal state."""
import json
from datetime import date, datetime
from pathlib import Path

from stockpilot.book import units
from stockpilot.jobs import doctor

NOW = datetime(2026, 11, 24, 20, 0)


def lot(db, symbol, isin, qty, closed=0, kind="stock", currency="INR"):
    db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, currency, closed_quantity, source) "
               "values (?, ?, ?, '2025-01-10', ?, 10, ?, ?, 'trades:test')", [kind, symbol, isin, qty, currency, closed])


def kite(db, symbol, isin, qty, kind="stock"):
    db.execute("insert into holdings values (?, ?, ?, ?, ?, 10, 'kite')", [datetime(2026, 11, 24, 9), kind, symbol, isin, qty])


class Gh:
    def __init__(self):
        self.calls = []

    def __call__(self, *args):
        self.calls.append(args)
        return "[]" if args[:2] == ("issue", "list") else "https://github.com/o/r/issues/9"


def test_matching_units_pass(db):
    lot(db, "TCS", "INE467B01029", 10)
    kite(db, "TCS", "INE467B01029", 10)
    assert units.gaps(db) == []


def test_every_difference_is_named_in_plain_words(db):
    lot(db, "TCS", "INE467B01029", 10)
    kite(db, "TCS", "INE467B01029", 12)                         # documents explain too little
    lot(db, "INFY", "INE009A01021", 5)                          # the documents think he still holds it; Kite does not
    kite(db, "NEWIPO", "INE000N01011", 50)                      # Kite holds it; no document at all
    lot(db, "PPFAS", "INF879O01027", 4890.044, kind="mf")
    kite(db, "INF879O01027", "INF879O01027", 7162.094, kind="mf")
    got = {g.isin: g.message for g in units.gaps(db)}
    assert got["INE467B01029"] == "TCS: Kite shows 12 units, the documents explain 10 (2 unexplained)."
    assert got["INE009A01021"] == "INFY: the documents show 5 units, Kite shows none (5 unexplained)."
    assert got["INE000N01011"] == "NEWIPO: Kite shows 50 units, no document explains any (50 unexplained)."
    assert got["INF879O01027"] == "PPFAS: Kite shows 7162.09 units, the documents explain 4890.04 (2272.05 unexplained)."


def test_sold_lots_do_not_count_and_us_shares_are_not_checked_against_kite(db):
    lot(db, "TCS", "INE467B01029", 10, closed=4)
    kite(db, "TCS", "INE467B01029", 6)
    lot(db, "NOW", "US81762P1021", 6, kind="rsu", currency="USD")
    assert units.gaps(db) == []


def test_with_no_kite_snapshot_there_is_nothing_to_check(db):
    lot(db, "TCS", "INE467B01029", 10)
    assert units.gaps(db) == []


def test_each_mismatch_is_a_problem_and_all_of_them_share_one_issue_through_the_doctor(db, tmp_path):
    lot(db, "TCS", "INE467B01029", 10)
    kite(db, "TCS", "INE467B01029", 12)
    kite(db, "NEWIPO", "INE000N01011", 50)
    gh = Gh()
    doctor.doctor(db, {}, NOW, tmp_path, gh)
    creates = [c for c in gh.calls if c[:2] == ("issue", "create") and "units-mismatch" in c[c.index("--title") + 1]]
    assert len(creates) == 1
    body = creates[0][creates[0].index("--body") + 1]
    assert "TCS: Kite shows 12 units" in body and "NEWIPO: Kite shows 50 units" in body
    assert db.execute("select count(*) from problems where job = 'units' and resolution is null").fetchone()[0] == 2
    gh2 = Gh()
    doctor.doctor(db, {}, NOW, tmp_path, gh2)
    assert not [c for c in gh2.calls if c[:2] == ("issue", "create") and "units-mismatch" in c[c.index("--title") + 1]]
    assert db.execute("select count(*) from problems where job = 'units' and resolution is null").fetchone()[0] == 2   # not doubled


def test_problems_and_the_issue_clear_when_the_units_agree(db, tmp_path):
    lot(db, "TCS", "INE467B01029", 10)
    kite(db, "TCS", "INE467B01029", 12)
    doctor.doctor(db, {}, NOW, tmp_path, Gh())
    db.execute("update holdings set quantity = 10")
    doctor.doctor(db, {}, NOW, tmp_path, Gh())
    assert db.execute("select resolution from problems where job = 'units'").fetchone()[0] == "cleared"
    assert db.execute("select resolution from problems where job = 'doctor' and message = 'units-mismatch'").fetchone()[0] == "cleared"
