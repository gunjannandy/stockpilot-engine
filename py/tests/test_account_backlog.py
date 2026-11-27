from datetime import date
from pathlib import Path

from pdfs import make_pdf
from stockpilot import journal, store
from stockpilot.trades import corporate_actions as ca
from stockpilot.trades import coin, feed, ipo, lots, rsu
from stockpilot.trades.lots import Trade
from test_trades_feed import FakeBridge, msg

FIX = Path(__file__).parent / "fixtures" / "trades"
PAN = "ABCDE1234F"
VISHAL = "INE01EA01019"
IPO_MAIL = FIX.joinpath("ipo_allotment.txt").read_text()
REDEMPTION = FIX.joinpath("coin_redemption.txt").read_text()


# --- IPO allotment mails -------------------------------------------------------------------------

def test_ipo_mail_gives_a_buy_at_the_issue_price_on_the_allotment_date():
    [t] = ipo.parse_email(IPO_MAIL, "Allotment received - Vishal Mega Mart Limited IPO", date(2024, 12, 19))
    assert (t.source, t.kind, t.side, t.quantity, t.price, t.trade_date) == ("ipo", "stock", "buy", 190.0, 78.0, date(2024, 12, 18))
    assert t.symbol == "Vishal Mega Mart Limited" and t.isin is None


def test_ipo_mail_other_wording_and_no_date_uses_the_mail_date():
    body = "Shares allotted: 12\nOffer price: Rs. 1,008.50\n"
    [t] = ipo.parse_email(body, "Allotment received: JPL IPO", date(2025, 3, 3))
    assert (t.symbol, t.quantity, t.price, t.trade_date) == ("JPL", 12.0, 1008.5, date(2025, 3, 3))


def test_ipo_mail_that_cannot_be_read_fails_loudly():
    import pytest
    with pytest.raises(ValueError):
        ipo.parse_email("Thank you for applying.", "Allotment received - X IPO", date(2025, 3, 3))


def test_feed_routes_ipo_and_redemption_mail_and_store_all_names_the_stock(tmp_path):
    bridge = FakeBridge([msg("i1", "Zerodha <a@zerodha.net>", "Allotment received - Vishal Mega Mart Limited IPO"),
                         msg("r1", "Coin <a@coinmailer.zerodha.net>", "Coin by Zerodha - Redemption Report -  04-05-2026")],
                        {}, {"i1": IPO_MAIL, "r1": REDEMPTION})
    result = feed.fetch(bridge, PAN, since=None, isin_of=lambda name: "INF879O01027")
    assert [t.source for t in result.trades] == ["ipo", "coin"] and result.ignored == [] and result.skipped == []
    db = store.open(tmp_path / "t.duckdb")
    db.execute("insert into stocks values ('VMM', 'Vishal Mega Mart Limited', 'Retail', ?)", [VISHAL])
    feed.store_all(db, result)
    assert db.execute("select symbol, isin from trades where source = 'ipo'").fetchall() == [("VMM", VISHAL)]
    assert db.execute("select side, quantity from trades where source = 'coin'").fetchall() == [("sell", 1.0)]


def test_ipo_that_matches_no_listed_stock_is_a_problem_not_a_guess(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    result = feed.FeedResult(trades=ipo.parse_email(IPO_MAIL, "Allotment received - Vishal Mega Mart Limited IPO", date(2024, 12, 19)))
    feed.store_all(db, result)
    assert "Vishal Mega Mart Limited" in db.execute("select message from problems").fetchone()[0]


def test_the_four_ipo_gaps_close_against_the_depository_statement(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    names = [("VMM", "Vishal Mega Mart Limited", "INE01EA01019", 190), ("JPL", "JPL Limited", "INE0BJO01010", 12),
             ("LGEIL", "LG Electronics India Limited", "INE324D01010", 13), ("JSWCEMENT", "JSW Cement Limited", "INE718I01012", 102)]
    trades = []
    for sym, name, isin, qty in names:
        db.execute("insert into stocks values (?, ?, 'x', ?)", [sym, name, isin])
        trades += ipo.parse_email(f"Shares allotted: {qty}\nIssue price: Rs. 100\nDate of allotment: 18 Dec 2024\n",
                                  f"Allotment received - {name} IPO", date(2024, 12, 19))
        db.execute("insert into holding_statements values ('2026-10-31', ?, ?)", [isin, qty])
    feed.store_all(db, feed.FeedResult(trades=trades))
    lots.rebuild(db)
    assert lots.check_against_statement(db) == (date(2026, 10, 31), [])


# --- Coin redemption -----------------------------------------------------------------------------

def test_redemption_mail_is_a_sell_at_amount_over_units():
    [t] = coin.parse_redemption(REDEMPTION, date(2024, 12, 10), isin_of=lambda name: "INF879O01027")
    assert (t.kind, t.side, t.isin, t.quantity, t.trade_date) == ("mf", "sell", "INF879O01027", 1.0, date(2024, 12, 10))
    assert round(t.price, 4) == 88.8 and t.trade_key == "mf:2024-12-10:INF879O01027:sell:1"


def test_redemption_reduces_the_units_held(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    lots.save_trades(db, [Trade("coin", "b", "mf", "PPFAS", "INF879O01027", "buy", date(2025, 1, 1), 1000.0, 80.0)]
                     + coin.parse_redemption(REDEMPTION, date(2025, 6, 1), isin_of=lambda name: "INF879O01027"))
    out = lots.rebuild(db)
    assert out.unmatched_sells == [] and round(lots.holdings(db)[0].quantity, 6) == round(1000.0 - 1.0, 6)


# --- demerger and rights, as corporate actions -----------------------------------------------------

def _hold(db, qty=10, cost=1000.0, on=date(2020, 1, 1)):
    lots.save_trades(db, [Trade("tradebook", "p", "stock", "PARENT", "INE000P01010", "buy", on, qty, cost, trade_key="p")])


def test_demerger_gives_a_child_lot_with_its_share_of_the_cost_and_the_parents_dates(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    _hold(db)
    ca.save(db, [ca.Action("PARENT", "INE000P01010", date(2023, 7, 20), "demerger", 1, 2, "Demerger", new_isin="INE000C01010",
                           new_symbol="CHILD", cost_fraction=0.1)])
    lots.rebuild(db)
    got = db.execute("select symbol, isin, acquired_on, quantity, cost_per_unit, source, source_ref from lots order by symbol").fetchall()
    assert got == [("CHILD", "INE000C01010", date(2020, 1, 1), 5.0, 200.0, "trades:demerger", "demerger:2023-07-20"),
                   ("PARENT", "INE000P01010", date(2020, 1, 1), 10.0, 900.0, "trades:tradebook", "p")]
    total = sum(q * c for _, _, _, q, c, _, _ in got)
    assert total == 10 * 1000.0       # the cost is split, not created
    lots.rebuild(db)                  # rebuilding again gives the same lots
    assert db.execute("select count(*) from lots").fetchone()[0] == 2


def test_child_sales_after_the_demerger_use_the_child_lot(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    _hold(db)
    lots.save_trades(db, [Trade("tradebook", "s", "stock", "CHILD", "INE000C01010", "sell", date(2024, 1, 5), 2.0, 300.0, trade_key="s")])
    ca.save(db, [ca.Action("PARENT", "INE000P01010", date(2023, 7, 20), "demerger", 1, 2, "Demerger", new_isin="INE000C01010",
                           new_symbol="CHILD", cost_fraction=0.1)])
    out = lots.rebuild(db)
    assert out.unmatched_sells == []
    assert db.execute("select closed_quantity from lots where symbol = 'CHILD'").fetchone()[0] == 2.0


def test_a_demerger_without_a_cost_split_is_ignored_not_guessed(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    _hold(db)
    ca.save(db, [ca.Action("PARENT", "INE000P01010", date(2023, 7, 20), "demerger", 1, 2, "Demerger", new_isin="INE000C01010",
                           new_symbol="CHILD")])
    lots.rebuild(db)
    assert db.execute("select symbol, cost_per_unit from lots").fetchall() == [("PARENT", 1000.0)]


def test_rights_issue_adds_a_lot_at_the_rights_price_on_the_allotment_date(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    _hold(db, qty=300, cost=100.0)
    ca.save(db, [ca.Action("PARENT", "INE000P01010", date(2025, 6, 10), "rights", 23, 100, "Rights 23:100", source="owner", price=60.0)])   # NSE rows add no lot (P1); the owner's entry does
    lots.rebuild(db)
    assert db.execute("select quantity, cost_per_unit, acquired_on, source_ref from lots order by acquired_on, id").fetchall() == [
        (300.0, 100.0, date(2020, 1, 1), "p"), (69.0, 60.0, date(2025, 6, 10), "rights:2025-06-10")]


def test_classify_credit_names_a_demerger_and_a_rights_credit():
    demerger = ca.Action("PARENT", "INE000P01010", date(2023, 7, 20), "demerger", 1, 2, "d", new_isin="INE000C01010", new_symbol="CHILD",
                         cost_fraction=0.1)
    rights = ca.Action("PARENT", "INE000P01010", date(2025, 6, 10), "rights", 23, 100, "r", price=60.0)
    assert ca.classify_credit([demerger], "INE000C01010", date(2023, 7, 21), 5, 10) == "demerger"
    assert ca.classify_credit([rights], "INE000P01010", date(2025, 6, 12), 69, 300) == "rights"
    assert ca.classify_credit([demerger, rights], "INE000P01010", date(2025, 7, 30), 69, 300) == "buy"   # too late to be either


# --- payslips and Form 16 --------------------------------------------------------------------------

SLIP = ["Pay Period: November 2026", "Basic 250,000.00", "RSU Perquisite 1,85,000.00", "Net Pay 3,10,000.00"]
FORM16 = ["Form 16 Part B  Assessment Year 2026-27", "Value of perquisites under section 17(2) 1,85,000.00"]


def drive(id, name):
    return {"source": "drive", "id": id, "name": name, "path": "Income Tax", "mime": "application/pdf"}


class PdfBridge(FakeBridge):
    def file(self, file_id):
        from stockpilot.sources import google
        self.fetched.append(file_id)
        return google.Blob("x.pdf", "application/pdf", self.blobs[file_id])


def test_drive_payslip_and_form16_are_parsed_into_perquisites():
    bridge = PdfBridge([drive("d1", "Payslip Nov 2026.pdf"), drive("d2", "Form16 2025-26.pdf")], {"d1": make_pdf(SLIP, PAN), "d2": make_pdf(FORM16, PAN)}, {})
    result = feed.fetch(bridge, PAN, since=None)
    assert result.failed == [] and [h["outcome"] for h in result.handled] == ["parsed", "parsed"]
    assert result.perquisites == [("payslip", "2026-11", 185000.0, "d1"), ("form16", "2025-26", 185000.0, "d2")]


def test_payslip_that_cannot_be_read_is_a_failed_document():
    bridge = PdfBridge([drive("d1", "Payslip Nov 2026.pdf")], {"d1": make_pdf(["Hello"], PAN)}, {})
    assert feed.fetch(bridge, PAN, since=None).failed[0][0] == "d1"


def _now(db, close_usd=800.0, rate=84.0):
    db.execute("insert into prices values ('2026-11-14', 'NOW', 'NYSE', 'EQ', ?, ?, ?, ?, null, 1, null, null)", [close_usd] * 4)
    db.execute("insert into fx values ('2026-11-14', 'USDINR', ?)", [rate])


def test_a_payslip_perquisite_becomes_an_expected_vest_never_a_lot(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    _now(db)
    feed.store_all(db, feed.FeedResult(perquisites=[("payslip", "2026-11", 185000.0, "d1")]))
    feed.store_all(db, feed.FeedResult(perquisites=[("payslip", "2026-11", 185000.0, "d1")]))   # a second sync adds nothing
    rows = db.execute("select side, status, trade_date, quantity, source from trades").fetchall()
    assert rows == [("vest", "expected", date(2026, 11, 15), round(185000 / (800 * 84), 4), "rsu_inference")]
    assert lots.rebuild(db).lots == 0


def test_no_price_for_the_month_leaves_the_vest_out_and_says_so(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    feed.store_all(db, feed.FeedResult(perquisites=[("payslip", "2026-11", 185000.0, "d1")]))
    assert db.execute("select count(*) from trades").fetchone()[0] == 0
    assert "ServiceNow" in db.execute("select message from problems").fetchone()[0]


def test_form16_total_is_checked_against_the_payslips_of_that_year(tmp_path):
    db = store.open(tmp_path / "t.duckdb")
    for day in ("2025-11-14", "2026-02-13"):
        db.execute("insert into prices values (?, 'NOW', 'NYSE', 'EQ', 800, 800, 800, 800, null, 1, null, null)", [day])
        db.execute("insert into fx values (?, 'USDINR', 84)", [day])
    feed.store_all(db, feed.FeedResult(perquisites=[("payslip", "2025-11", 100000.0, "a"), ("payslip", "2026-02", 85000.0, "b"),
                                                    ("form16", "2025-26", 185000.0, "c")]))
    assert db.execute("select count(*) from problems").fetchone()[0] == 0
    feed.store_all(db, feed.FeedResult(perquisites=[("form16", "2025-26", 400000.0, "c")]))
    assert "2025-26" in db.execute("select message from problems").fetchone()[0]


def test_ipo_real_mail_layout_subject_company_first_and_price_after_at_a_price_of():
    body = FIX.joinpath("ipo_allotment_real.txt").read_text()
    [t] = ipo.parse_email(body, "Jio Platforms IPO - Allotment received", date(2026, 10, 27))
    assert (t.symbol, t.side, t.quantity, t.price, t.trade_date) == ("Jio Platforms", "buy", 12.0, 1119.0, date(2026, 10, 27))
    [t] = ipo.parse_email(body, "LG Electronics India - Allotment received", date(2025, 10, 13))
    assert t.symbol == "LG Electronics India"


def test_real_payslip_layout_month_and_stock_gain():
    text = FIX.joinpath("payslip_real.txt").read_text()
    assert rsu.parse_payslip(text) == ("2023-03", 120000.0)
    assert rsu.parse_payslip(text.replace("120,000.00", "0.00")) == ("2023-03", 0.0)


def test_real_form16_layout_perquisite_is_line_b_after_the_17_1_a_salary_line():
    text = FIX.joinpath("form16_real.txt").read_text()
    assert rsu.parse_form16(text) == ("2025-26", 1171347.0)
    # a certificate with no "Financial Year :" header still names its year in the certificate line
    no_header = "\n".join(line for line in text.splitlines() if not line.startswith(("Financial", "Assessment")))
    assert rsu.parse_form16(no_header) == ("2025-26", 1171347.0)
