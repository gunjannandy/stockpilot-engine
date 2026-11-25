from datetime import date
from pathlib import Path

import pytest

from pdfs import make_pdf
from stockpilot.trades import cas, coin, contract_note, fidelity

FIX = Path(__file__).parents[1] / "fixtures" / "trades"
NOTE = FIX.joinpath("contract_note_2026.txt").read_text().splitlines()   # real layout, redacted


def note(name):
    return contract_note.parse_text(FIX.joinpath(f"contract_note_{name}.txt").read_text())


def test_contract_note_pdf_with_pan_password():
    pdf = make_pdf(NOTE, password="ABCDE1234F")
    trades = contract_note.parse_pdf(pdf, "ABCDE1234F")
    assert [(t.isin, t.side, t.quantity, t.price, t.trade_date, t.trade_key) for t in trades] == [
        ("INE01R501028", "buy", 300.0, 67.1, date(2026, 8, 12), "607396242")]
    assert trades[0].symbol == "VIKRAN" and trades[0].source == "contract_note"


def test_contract_note_2023_layout_with_exchange_column_and_sub_totals():
    got = [(t.isin, t.side, t.quantity, t.price, t.trade_key) for t in note("2023")]
    assert got[0] == ("INE372A01015", "buy", 3.0, 3147.75, "233061")
    assert ("INE914M01019", "sell", 41.0, 298.0, "215849") in got
    assert len(got) == 7 and {t.trade_date for t in note("2023")} == {date(2023, 6, 16)}


def test_contract_note_2020_layout_has_name_and_isin_on_separate_lines():
    got = [(t.isin, t.side, t.quantity, t.price, t.trade_date) for t in note("2020")]
    assert got == [("INE090A01021", "buy", 10.0, 388.3, date(2020, 10, 8)),
                   ("INE062A01020", "buy", 10.0, 194.95, date(2020, 10, 8))]


def test_contract_note_2021_name_wraps_over_lines_and_date_comes_after_the_rows():
    assert [(t.symbol, t.isin, t.quantity, t.price, t.trade_date) for t in note("2021")] == [
        ("RELIANCE", "INE002A01018", 3.0, 2184.8, date(2021, 6, 24))]


def test_contract_note_wrong_password_is_a_clear_error():
    with pytest.raises(ValueError, match="password"):
        contract_note.parse_pdf(make_pdf(NOTE, password="ABCDE1234F"), "WRONGPAN00X")


def test_contract_note_without_trades_returns_nothing():
    assert contract_note.parse_text("Trade Date: 20/11/2026\nnothing here") == []


COIN_BUY = FIX.joinpath("coin_allotment.txt").read_text()   # real "Allotment Report" mail, redacted


def test_coin_allotment_report_gives_a_mutual_fund_buy_at_amount_over_units():
    [buy] = coin.parse_email(COIN_BUY)
    assert (buy.kind, buy.side, buy.quantity, buy.trade_date, buy.isin) == ("mf", "buy", 215.789, date(2025, 7, 1), None)
    assert buy.price == round(19999.0 / 215.789, 4)    # the Console tradebook's cost per unit, stamp duty included
    assert buy.symbol == "PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN GROWTH"
    assert buy.trade_key == "mf:2025-07-01:PARAG PARIKH FLEXI CAP FUND - DIRECT PLAN GROWTH:buy:215.789"


def test_coin_resolves_the_isin_from_the_fund_name_when_given_a_lookup():
    [buy] = coin.parse_email(COIN_BUY, isin_of=lambda name: "INF879O01027")
    assert buy.isin == "INF879O01027" and buy.trade_key == "mf:2025-07-01:INF879O01027:buy:215.789"


def test_coin_ignores_other_mail():
    assert coin.parse_email("Your Coin statement is ready. Open the app.") == []


def test_cas_holding_statement_gives_quantity_per_isin_on_the_statement_date():
    stmt = cas.parse_text(FIX.joinpath("cas_holdings.txt").read_text())
    assert stmt.as_of == date(2026, 10, 31)
    assert stmt.closing == {"INE0LRU01027": 25.0, "INE742F01042": 59.0, "INE055A01016": 10.0,
                            "INE059A01026": 10.0, "INE491A01021": 649.0, "INE220Q01020": 50.0}


FID_VEST = ("Your ServiceNow, Inc. (NOW) restricted stock units have vested. Vest date: 11/15/2026. "
            "Shares vested: 25. Shares withheld for taxes: 9. Net shares deposited: 16. Fair market value per share: $145.20. Reference RSU-5512.")
FID_SALE = "You sold 10 shares of NOW on 12/01/2026 at $150.00 per share. Confirmation 77123."


def test_fidelity_vest_keeps_net_shares_at_vest_fmv():
    t = fidelity.parse_email(FID_VEST)
    assert (t.side, t.kind, t.symbol, t.quantity, t.price, t.currency, t.trade_date, t.status) == (
        "vest", "rsu", "NOW", 16.0, 145.2, "USD", date(2026, 11, 15), "confirmed")
    assert t.isin == "US81762P1021"


def test_fidelity_sale():
    t = fidelity.parse_email(FID_SALE)
    assert (t.side, t.symbol, t.quantity, t.price, t.trade_date) == ("sell", "NOW", 10.0, 150.0, date(2026, 12, 1))


def test_fidelity_ignores_marketing():
    assert fidelity.parse_email("Market update: tech stocks rally.") is None
