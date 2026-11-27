"""A code check on each _bn field (summary_bn, market_view_bn): Bengali the owners can read, the same numbers as the English."""
import pytest

from stockpilot.calls import bn

EN = "Wipro: profit is up 12% and the price is ₹1,250."


def test_a_good_bengali_sentence_passes_with_english_names_kept():
    assert bn.problems(EN, "Wipro: মুনাফা ১২% বেড়েছে এবং দাম ₹১,২৫০।") == []
    assert bn.problems(EN, "Wipro-র মুনাফা 12% বেড়েছে, দাম ₹1,250।") == []


@pytest.mark.parametrize("text,why", [
    ("", "empty"), ("   ", "empty"),
    (EN, "same as the English"),
    ("Wipro profit up 12 percent price 1,250", "not Bengali"),
    ("Wipro: मुनाफा 12% बढ़ा, दाम ₹1,250।", "Hindi"),
    ("Wipro: মুনাফা বেড়েছে এবং দাম বেড়েছে।", "numbers missing"),
    ("Wipro: মুনাফা 13% বেড়েছে, দাম ₹1,250।", "number changed"),
])
def test_a_bad_field_is_named(text, why):
    got = bn.problems(EN, text)
    assert got, why


def test_no_numbers_in_the_english_asks_nothing_of_the_bengali():
    assert bn.problems("Nothing to do today.", "আজ কিছু করার নেই।") == []


def test_bengali_digits_count_as_the_same_number():
    assert bn.numbers("১২.৫% এবং ₹১,২৫০") == bn.numbers("12.5% and ₹1,250") == ["12.5", "1250"]


def test_clean_returns_the_text_or_blank_and_the_reason():
    assert bn.clean(EN, "Wipro: মুনাফা ১২% বেড়েছে, দাম ₹১,২৫০।") == ("Wipro: মুনাফা ১২% বেড়েছে, দাম ₹১,২৫০।", [])
    text, why = bn.clean(EN, "wrong")
    assert text == "" and why
