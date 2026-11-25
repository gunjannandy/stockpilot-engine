"""Fidelity documents (year-end report, monthly stock plan statements, transaction summary, 1042-S): RSU vests and
sales, and the stage 7 reconciliation with the vests and sales we hold. Fixtures keep the real layouts with an invented
person and made-up amounts (the nine real files were read on the VM; see docs/status/R18.md)."""
from datetime import date
from pathlib import Path

import pytest

from stockpilot import backup, store
from stockpilot.trades import fidelity_docs as fd

FIX = Path(__file__).parents[1] / "fixtures" / "trades"


def read(name):
    return (FIX / name).read_text()


def test_year_end_report_gives_each_vest_with_gross_net_and_fair_value():
    doc = fd.parse_text(read("fidelity_year_end.txt"))
    assert doc.kind == "year_end"
    assert [(e.event_date, e.grant_id, e.quantity, e.net_quantity, e.price_usd) for e in doc.events] == [
        (date(2025, 2, 7), "21RUIN4.4", 3, 3, 800.50), (date(2025, 2, 14), "22RUIN13", 7, 5, 790.25),
        (date(2025, 5, 16), "22RUIN13", 8, 8, 832.15), (date(2025, 11, 17), "22RUIN13", 7, 7, 668.60)]
    assert {e.kind for e in doc.events} == {"vest"}      # grants and the stock split rows are not vests


def test_monthly_statements_give_shares_deposited_and_sales_with_the_year_of_their_period():
    doc = fd.parse_text(read("fidelity_statement.txt"))
    assert doc.kind == "statement"
    vests = [(e.event_date, e.quantity, e.net_quantity, e.price_usd, e.amount_usd) for e in doc.events if e.kind == "vest"]
    assert vests == [(date(2024, 5, 21), 5, 5, 700.0, 3500.0), (date(2024, 8, 19), 5, 5, 840.0, 4200.0)]
    sales = [(e.event_date, e.quantity, e.price_usd, e.cost_usd, e.amount_usd) for e in doc.events if e.kind == "sale"]
    assert sales == [(date(2024, 5, 22), 2, 706.25, 1400.0, 1412.43), (date(2024, 8, 20), 2, 830.0, 1660.0, 1657.93)]


def test_transaction_summary_gives_each_sale_with_the_vest_it_came_from():
    doc = fd.parse_text(read("fidelity_transaction_summary.txt"))
    assert doc.kind == "transaction_summary"
    assert [(e.event_date, e.acquired_on, e.quantity, e.cost_usd, e.amount_usd) for e in doc.events] == [
        (date(2024, 5, 20), date(2024, 5, 17), 2, 1400.0, 1412.43), (date(2024, 8, 19), date(2024, 8, 17), 2, 1660.0, 1657.93)]


def test_1042s_gives_the_tax_year_and_the_gross_income():
    doc = fd.parse_text(read("fidelity_1042s.txt"))
    assert doc.kind == "form_1042s"
    assert [(e.kind, e.event_date, e.amount_usd) for e in doc.events] == [("dividend", date(2024, 12, 31), 4.0)]


def test_a_document_that_is_not_fidelity_fails_loudly_and_the_holdings_export_says_why():
    with pytest.raises(ValueError, match="not a Fidelity"):
        fd.parse_text("Dear customer")
    with pytest.raises(ValueError, match="holdings export"):
        fd.parse_text("CSV Export\nGenerated on: 31/12/2025 17:19:03\nDate ac\nquired")


def test_a_statement_with_no_activity_has_no_events_and_is_not_an_error():
    assert fd.parse_text("STOCK PLAN SERVICES REPORT\nFebruary 1, 2026 - February 28, 2026\nAccount Summary\n").events == []


def test_save_replaces_one_documents_rows_and_the_table_is_in_state_backup(tmp_path):
    db = store.open(tmp_path / "a.duckdb")
    doc = fd.parse_text(read("fidelity_year_end.txt"))
    fd.save(db, doc, "f1")
    fd.save(db, doc, "f1")
    assert db.execute("select count(*) from fidelity_events").fetchone()[0] == 4
    assert "fidelity_events" in backup.STATE_TABLES


# --- the stage 7 reconciliation with the vests and sales we hold -------------------------------------------------

def trade(db, side, day, qty, status="confirmed", source="fidelity"):
    db.execute("insert into trades (trade_key, source, source_ref, kind, symbol, isin, side, trade_date, quantity, price, "
               "currency, status) values (?,?,?,?,?,?,?,?,?,?,?,?)",
               [f"{side}:{day}:{status}", source, "x", "rsu", "NOW", "US81762P1021", side, day, qty, 1.0, "USD", status])


def sale(db, day, qty):
    db.execute("insert into sales (kind, symbol, isin, sold_on, quantity, price_per_unit, currency, source) "
               "values ('rsu','NOW','US81762P1021',?,?,1.0,'USD','fidelity')", [day, qty])


def seeded(tmp_path):
    db = store.open(tmp_path / "a.duckdb")
    fd.save(db, fd.parse_text(read("fidelity_year_end.txt")), "f1")
    trade(db, "vest", date(2025, 2, 7), 3)                                    # agrees
    trade(db, "vest", date(2025, 2, 14), 7)                                   # Fidelity deposited 5 after withholding 2
    trade(db, "vest", date(2025, 11, 15), 7, status="expected", source="rsu_inference")   # inferred, a vest on the 17th: agrees
    trade(db, "vest", date(2025, 8, 15), 7, status="expected", source="rsu_inference")    # inferred, no Fidelity vest in August
    return db                                                                 # 16 May 2025: Fidelity has it, we do not


def test_reconcile_counts_agreeing_vests_and_says_each_disagreement_in_words(tmp_path):
    result = fd.reconcile(seeded(tmp_path))
    assert result.vests_matched == 2
    assert len(result.notes) == 3
    joined = " ".join(result.notes)
    assert "14 Feb 2025" in joined and "5 " in joined and "7 vested" in joined and "says 7" in joined
    assert "16 May 2025" in joined and "no record" in joined
    assert "15 Aug 2025" in joined and "expect" in joined and "Fidelity" in joined


def test_reconcile_compares_sales_and_prefers_the_transaction_summary_over_the_statement_date(tmp_path):
    db = store.open(tmp_path / "a.duckdb")
    fd.save(db, fd.parse_text(read("fidelity_statement.txt")), "s1")
    fd.save(db, fd.parse_text(read("fidelity_transaction_summary.txt")), "t1")
    sale(db, date(2024, 5, 20), 2)                      # agrees (the statement shows the settlement day, two days later)
    result = fd.reconcile(db)
    assert result.sales_matched == 1
    sale_notes = [n for n in result.notes if "sale" in n]
    assert len(sale_notes) == 1 and "19 Aug 2024" in sale_notes[0] and "no record" in sale_notes[0]


def test_reconcile_with_no_fidelity_documents_has_nothing_to_say(tmp_path):
    result = fd.reconcile(store.open(tmp_path / "a.duckdb"))
    assert (result.notes, result.vests_matched, result.sales_matched) == ([], 0, 0)


def test_weekly_notes_carry_the_fidelity_check_and_never_fail(tmp_path):
    from stockpilot import weekly
    db = seeded(tmp_path)
    assert len(weekly.fidelity_notes(db)) == 3
    db.close()
    assert weekly.fidelity_notes(db)[0].startswith("The check against Fidelity")
