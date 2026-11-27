"""Income tax return documents (ITR acknowledgement, filled-up return, 143(1) intimation, annual tax statement) and the
stage 7 check of the return against Console and our lots. Fixtures are the real layouts with invented people and
scaled amounts (the real files were read on the VM; see docs/status/R18.md)."""
from datetime import date
from pathlib import Path

import pytest

from stockpilot import backup, store
from stockpilot.trades import consolepnl, itr

FIX = Path(__file__).parents[1] / "fixtures" / "trades"
PAN = "AAAAA0000A"


def read(name):
    return (FIX / name).read_text()


def test_acknowledgement_gives_the_year_totals_and_what_was_paid():
    doc = itr.parse_text(read("itr_ack.txt"), pan=PAN)
    assert (doc.kind, doc.assessment_year, doc.fy, doc.form) == ("acknowledgement", "2026-27", "2025-26", "ITR-2")
    assert doc.filed_on == date(2026, 7, 11)
    assert (doc.total_income, doc.tax_payable, doc.interest_fees) == (2612465, 653617, 609)
    assert (doc.taxes_paid, doc.balance_due, doc.refund) == (654225, 0, 0)   # one rupee apart, and the form says nothing is due
    assert doc.for_owner is True


def test_filled_return_gives_capital_gains_by_head_and_the_foreign_assets_schedule():
    doc = itr.parse_text(read("itr_return_excerpt.txt"), pan=PAN)
    assert (doc.kind, doc.assessment_year, doc.form) == ("return", "2026-27", "ITR-2")
    assert (doc.stcg_equity, doc.stcg_total, doc.ltcg_equity, doc.ltcg_total) == (-50202, -45202, 58188, 60188)
    assert doc.capital_gains_head == 14986 and doc.total_income == 2612465
    assert (doc.tax_payable, doc.taxes_paid, doc.tds_credited, doc.refund, doc.balance_due) == (653617, 654225, 646865, 0, 0)
    assert doc.fa_present is True and doc.fa_entries == 0      # the schedule is in the form, with no row filled


def test_a_foreign_assets_row_is_counted():
    text = read("itr_return_excerpt.txt").replace("on 31st December, 2025\nSl.\nNo.\nCountry\n",
                                                  "on 31st December, 2025\nSl.\nNo.\nCountry\n1\n2-United States Of America\nEXAMPLE ENTITY\n")
    assert itr.parse_text(text, pan=PAN).fa_entries == 1


def test_intimation_gives_the_processed_figures_and_the_capital_gains_head():
    doc = itr.parse_text(read("itr_intimation_en.txt"), pan=PAN)
    assert (doc.kind, doc.assessment_year, doc.fy, doc.form) == ("intimation", "2025-26", "2024-25", "ITR-2")
    assert doc.filed_on == date(2025, 10, 11)
    assert (doc.total_income, doc.tax_payable, doc.interest_fees, doc.taxes_paid) == (2512270, 631561, 1354, 632916)
    assert doc.capital_gains_head == 0 and doc.refund == 0 and doc.balance_due == 0


def test_annual_tax_statement_adds_up_tds_and_says_when_it_is_not_the_owners():
    doc = itr.parse_text(read("annual_tax_statement.txt"), pan=PAN)
    assert (doc.kind, doc.assessment_year, doc.fy) == ("tax_statement", "2025-26", "2024-25")
    assert doc.tds_credited == pytest.approx(9710.20) and doc.for_owner is False


def test_a_document_that_is_no_return_fails_loudly():
    with pytest.raises(ValueError, match="not an income tax return"):
        itr.parse_text("Dear customer, your statement is ready.", pan=PAN)


def test_a_return_with_no_total_income_fails_loudly_instead_of_storing_zero():
    with pytest.raises(ValueError, match="total income"):
        itr.parse_text(read("itr_return_excerpt.txt").replace("Total income (9 - 11)", "Total revenue"), pan=PAN)


def test_documents_of_one_year_are_stored_once_each_and_merged_on_load(tmp_path):
    db = store.open(tmp_path / "a.duckdb")
    itr.save(db, itr.parse_text(read("itr_ack.txt"), PAN), "a1", "m1")
    itr.save(db, itr.parse_text(read("itr_ack.txt"), PAN), "a1", "m2")                  # same file again: still one row
    itr.save(db, itr.parse_text(read("itr_return_excerpt.txt"), PAN), "r1", "m1")
    itr.save(db, itr.parse_text(read("annual_tax_statement.txt"), PAN), "s1", "m1")     # another person's PAN
    assert db.execute("select count(*) from itr_documents").fetchone()[0] == 3
    merged = itr.load(db, "2026-27")
    assert merged.stcg_equity == -50202 and merged.filed_on == date(2026, 7, 11) and merged.fa_entries == 0
    assert itr.load(db, "2025-26") is None          # only the other person's statement is on file for that year


def test_the_new_tables_are_in_state_backup():
    assert {"itr_documents", "fidelity_events"} <= set(backup.STATE_TABLES)


# --- the stage 7 check: the filed return against Console and our lots ------------------------------------------

def our(kind, term, bucket, proceeds, cost, sold=date(2025, 8, 1)):
    return {"kind": kind, "term": term, "bucket": bucket, "proceeds": proceeds, "cost": cost, "sold_on": sold,
            "gain": proceeds - cost}


def filed_db(tmp_path, with_console=True):
    db = store.open(tmp_path / "a.duckdb")
    itr.save(db, itr.parse_text(read("itr_return_excerpt.txt"), PAN), "r1", "2026-07-18T00:00:00Z")
    itr.save(db, itr.parse_text(read("itr_ack.txt"), PAN), "a1", "2026-07-18T00:00:00Z")
    if with_console:
        for seg, cat, profit in [("equity", "short_term", -50202.0), ("equity", "intraday", 900.0),
                                 ("equity", "long_term", 40000.0), ("mf", "long_term_equity", 18188.0)]:
            db.execute("insert into console_pnl_totals values ('2025-26', ?, ?, ?, '2026-03-21', 'c1', '')", [seg, cat, profit])
    return db


MATCHING = [our("stock", "short", "equity", 50000, 100202), our("stock", "long", "equity", 90000, 50000),
            our("mf", "long", "equity", 20188, 2000)]


def test_check_is_silent_when_the_return_agrees_with_console_and_our_lots(tmp_path):
    assert itr.check(filed_db(tmp_path), 2025, MATCHING, foreign_lots=0) == []


def test_check_says_where_the_return_and_our_lots_part_ways_in_plain_words(tmp_path):
    ours = [our("stock", "short", "equity", 50000, 80000)] + MATCHING[1:]      # short-term -30,000, the return says -50,202
    notes = itr.check(filed_db(tmp_path), 2025, ours, foreign_lots=0)
    assert len(notes) == 1
    assert "2025-26" in notes[0] and "short-term gain on shares" in notes[0]
    assert "-₹50,202" in notes[0] and "our lots give -₹30,000" in notes[0] and "Console" not in notes[0]   # Console agrees


def test_check_flags_an_empty_foreign_assets_schedule_when_we_hold_foreign_shares(tmp_path):
    notes = itr.check(filed_db(tmp_path), 2025, MATCHING, foreign_lots=3)
    assert len(notes) == 1 and "Schedule FA" in notes[0] and "foreign shares" in notes[0]


def test_check_notes_a_return_with_no_capital_gains_when_console_shows_a_gain(tmp_path):
    db = store.open(tmp_path / "a.duckdb")
    itr.save(db, itr.parse_text(read("itr_intimation_en.txt"), PAN), "i1", "")
    db.execute("insert into console_pnl_totals values ('2024-25', 'equity', 'long_term', 80000, '2025-03-31', 'c1', '')")
    assert itr.check(db, 2024, [], foreign_lots=0) == []        # under the Rs 1.25 lakh exemption: nothing taxable is right
    db.execute("update console_pnl_totals set profit = 200000")
    notes = itr.check(db, 2024, [], foreign_lots=0)
    assert len(notes) == 1 and "2024-25" in notes[0] and "no capital gains" in notes[0] and "₹200,000" in notes[0]


def test_check_has_nothing_to_say_for_a_year_with_no_return_on_file(tmp_path):
    assert itr.check(store.open(tmp_path / "a.duckdb"), 2025, [], foreign_lots=0) == []


