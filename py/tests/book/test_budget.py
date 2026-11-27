"""The month's budget: set from the dashboard, read by the calls and by the page from the same place."""
from datetime import date

import pytest

from stockpilot import store
from stockpilot.book import budget


@pytest.fixture
def db(tmp_path):
    return store.open(tmp_path / "t.duckdb")


def test_a_month_without_a_budget_uses_the_default(db):
    assert budget.for_month(db, date(2026, 12, 5), default=100_000) == 100_000


def test_the_latest_budget_for_the_month_wins_and_the_next_month_resets(db):
    budget.set_month(db, "2026-12", 50_000, by="father")
    budget.set_month(db, "2026-12", 70_000, by="owner")
    assert budget.for_month(db, date(2026, 12, 31), default=100_000) == 70_000
    assert budget.for_month(db, date(2027, 1, 1), default=100_000) == 100_000


@pytest.mark.parametrize("month, amount, why", [("2026-13", 5, "Month"), ("2026-12", 0, "above zero"),
                                                ("2026-12", True, "above zero"), ("2026-12", "9", "above zero")])
def test_a_bad_budget_is_refused_in_plain_words(db, month, amount, why):
    with pytest.raises(ValueError, match=why):
        budget.set_month(db, month, amount, by="father")
