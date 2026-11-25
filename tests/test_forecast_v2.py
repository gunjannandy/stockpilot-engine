"""Lane E: the stricter Sell end to end. The analyst states a broken reason; a mark makes a holding Review; one weak quarter
does not sell; sell_kind is a field on the stored call and the site reads it (no text match)."""
import json
from datetime import date

from forecast_seed import AS_OF
from stockpilot import forecast
from test_forecast import db, fake_analyse, go, rows, template   # noqa: F401
from test_r10_followups import quarter


def reasons(db, symbol):
    return json.loads(db.execute("select reasons from calls where symbol = ? and made_on = ?", [symbol, AS_OF]).fetchone()[0])


def test_an_analyst_stated_broken_reason_makes_a_sell_and_is_stored_on_the_call(db):
    go(db, fake_analyse({"analyst": {"WIPRO": 0.55}}, WIPRO={"broken_reason": "the auditor resigned"}))
    assert rows(db)["WIPRO"]["section"] == "sell"
    r = reasons(db, "WIPRO")
    assert r["sell_kind"] == "sell" and "auditor resigned" in r["why_code"]
    card = next(c for c in forecast.site_payload(db, AS_OF)["sells"] if c["symbol"] == "WIPRO")
    assert card["sell_kind"] == "sell"


def test_a_low_chance_alone_is_weak(db):
    go(db, fake_analyse({"analyst": {"WIPRO": 0.30}}))
    assert reasons(db, "WIPRO")["sell_kind"] == "weak"
    assert next(c for c in forecast.site_payload(db, AS_OF)["sells"] if c["symbol"] == "WIPRO")["sell_kind"] == "weak"


def test_a_long_term_mark_makes_a_weak_holding_review(db):
    db.execute("insert into long_term_marks (symbol, marked_by) values ('WIPRO', 'papa')")
    seen = []
    go(db, fake_analyse({"analyst": {"WIPRO": 0.30}}, seen=seen))
    assert reasons(db, "WIPRO")["sell_kind"] == "review"
    stocks = {s["symbol"]: s for _, b in seen for s in b["stocks"]}
    assert stocks["WIPRO"]["holding"]["long_term_mark"] is True


def test_an_unmarked_holding_has_no_mark_in_the_brief(db):
    seen = []
    go(db, fake_analyse(seen=seen))
    stocks = {s["symbol"]: s for _, b in seen for s in b["stocks"]}
    assert "long_term_mark" not in stocks["WIPRO"]["holding"]


def test_a_one_quarter_profit_dip_no_longer_sells_a_holding(db):
    quarter(db, "ITC", date(2025, 9, 30), 100.0)
    quarter(db, "ITC", date(2026, 9, 30), 50.0)
    seen = []
    go(db, fake_analyse(default=0.50, seen=seen))
    assert rows(db)["ITC"]["section"] == "hold"
    stocks = {s["symbol"]: s for _, b in seen for s in b["stocks"]}
    assert any("profit" in w for w in stocks["ITC"]["why_here"])        # the analyst is told, and judges it


def test_a_one_quarter_dip_with_a_low_chance_is_weak_not_sell(db):
    quarter(db, "ITC", date(2025, 9, 30), 100.0)
    quarter(db, "ITC", date(2026, 9, 30), 50.0)
    go(db, fake_analyse({"analyst": {"ITC": 0.30}, "skeptic": {"ITC": 0.30}}))
    assert reasons(db, "ITC")["sell_kind"] == "weak"


def test_a_holding_under_5000_rupees_never_sells(db):
    db.execute("update holdings set quantity = 1 where symbol = 'WIPRO'")
    db.execute("update lots set quantity = 1 where symbol = 'WIPRO'")
    go(db, fake_analyse({"analyst": {"WIPRO": 0.20}}, WIPRO={"broken_reason": "fraud"}))
    assert rows(db)["WIPRO"]["section"] == "hold"


def test_the_site_reads_sell_kind_from_the_stored_field_not_the_reason_text():
    from stockpilot.site_export import calls
    cards = [{"symbol": "A", "section": "sell", "sell_kind": "sell", "why": "Its chance is 30%."},
             {"symbol": "B", "section": "sell", "sell_kind": "weak", "why": "The reason for owning it has broken: x"},
             {"symbol": "C", "section": "sell", "sell_kind": "review", "why": None},
             {"symbol": "D", "section": "trim", "why": None},
             {"symbol": "E", "section": "sell", "why": "It fell to its stop (₹90); sell."},     # an old stored call: no field
             {"symbol": "F", "section": "buy", "sell_kind": "sell"}]
    calls.annotate(cards, "section")
    assert [c["sell_kind"] for c in cards] == ["sell", "weak", "review", "sell", "weak", None]


def test_a_bad_bengali_field_is_blanked_and_the_run_says_so(db):
    out = go(db, fake_analyse({"analyst": {"WIPRO": 0.55}}, WIPRO={"summary_bn": "Wipro is fine, nothing to do."}))
    assert rows(db)["WIPRO"]["summary_bn"] in (None, "")
    assert rows(db)["ICICIBANK"]["summary_bn"]                         # the good ones stay
    assert any(x.startswith("WIPRO summary_bn") for x in out["bn_rejected"])


def test_a_bad_market_view_bn_is_blanked(db):
    def analyse(brief, role, runners, **kw):
        got = fake_analyse()(brief, role, runners)
        got["decisions"]["market_view_bn"] = "Calm market."
        return got
    out = go(db, analyse)
    assert out["market_view_bn"] == "" and any(x.startswith("market_view_bn") for x in out["bn_rejected"])
