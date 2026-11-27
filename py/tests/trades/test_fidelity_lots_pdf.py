"""Lane R item 1: the 'Current Shares' table of the Fidelity Stock Plan export, read by word position. Fixture numbers are made up."""
from datetime import date

from stockpilot.trades import fidelity_lots

from fidelity_pdf import ROWS, make

def test_reads_each_lot_across_wrapped_cells():
    lots = fidelity_lots.parse_pdf(make(ROWS))
    assert [(l.acquired_on, l.quantity, l.cost_basis_inr, l.value_inr, l.term) for l in lots] == [
        (date(2024, 8, 17), 10.0, 100000.10, 120000.20, "long"),
        (date(2025, 11, 17), 5.5, 60000.0, 55000.0, "short")]
    assert lots[0].cost_per_share_inr == 10000.01 and lots[1].gain_inr == -5000.0
    assert lots[0].grant_date == date(2024, 3, 1) and lots[0].source == "RSU"


def test_agrees_with_holding_when_shares_and_cost_match():
    lots = fidelity_lots.parse_pdf(make(ROWS))
    assert fidelity_lots.agrees(lots, 15.5, 160000.10)
    assert not fidelity_lots.agrees(lots, 16.0, 160000.10)
    assert not fidelity_lots.agrees(lots, 15.5, 170000.0)
    assert not fidelity_lots.agrees([], 0, 0)
