"""Base rates for held stocks come from the stock's own price history, whatever the screen did with it."""
from datetime import date

from helpers import insert_prices
from stockpilot.analysis import held_base_rate as hb
from test_screen import AS_OF, series

RATES = {(m, r, v, l): {"n": 400 + m, "hit_rate": 0.40 + 0.02 * m}
         for m in range(5) for r in ("nifty_up", "nifty_down") for v in ("calm", "jumpy") for l in ("large", "small")}


def pool():
    """What the screen kept: momentum figures for a handful of stocks."""
    return {f"S{i}": {"metrics": {"ret_12m": 0.05 * i, "ret_6m": 0.03 * i, "dist_200dma": 0.02 * i, "vol_1y": 0.2 + 0.02 * i,
                                  "adv_3m_cr": 50.0}} for i in range(10)}


def look(db, symbol="HELD", **kw):
    args = dict(rates=RATES, regime="nifty_up", candidates=pool(), median_vol=0.25, floor_cr=1.0)
    return hb.for_held(db, symbol, AS_OF, **{**args, **kw})


def test_an_illiquid_held_stock_gets_a_base_rate_from_its_own_history_and_an_illiquid_line(db):
    series(db, "HELD", 0.002, value=1.2e6, days=300)             # about 0.12 crore a day, screened out
    got = look(db)
    assert got["n"] >= 30 and got["n"] != 0
    assert got["rate"] != 0.5
    assert "illiquid" in got["risk_line"].lower() or "thinly traded" in got["risk_line"].lower()
    assert "sell" in got["risk_line"].lower()                   # says plainly it is not a reason to sell by itself
    assert got["limited"] is False


def test_a_stock_on_an_exchange_watch_list_gets_a_plain_line_with_the_stage(db):
    series(db, "HELD", 0.002, value=5e8, days=300)
    db.execute("insert into surveillance values (?, 'HELD', 'STASM I')", [AS_OF])
    got = look(db)
    assert got["n"] >= 30
    assert "short-term watch list" in got["risk_line"] and "stage I" in got["risk_line"]


def test_a_gsm_label_is_named_gsm(db):
    series(db, "HELD", 0.002, value=5e8, days=300)
    db.execute("insert into surveillance values (?, 'HELD', 'GSM Stage 2')", [AS_OF])
    assert "graded watch list" in look(db)["risk_line"] and "stage 2" in look(db)["risk_line"]


def test_call_text_never_uses_a_word_plain_words_bans(db):
    from stockpilot.calls import runner
    series(db, "HELD", 0.002, value=1.2e6, days=300)
    db.execute("insert into surveillance values (?, 'HELD', 'LTASM II')", [AS_OF])
    got = look(db)
    assert runner.jargon_in(got["risk_line"] + " " + got["limited_line"]) == []


def test_the_coarse_table_is_used_when_the_40_bucket_one_is_empty(db):
    series(db, "HELD", 0.002, value=5e8, days=300)
    coarse = {("momentum", b, r): {"n": 800, "hit_rate": 0.45} for b in range(5) for r in ("nifty_up", "nifty_down")}
    got = look(db, rates=coarse)
    assert got["n"] == 800 and got["rate"] == 0.45


def test_a_stock_the_screen_scored_keeps_the_screens_rate_and_gets_only_the_lines(db):
    series(db, "HELD", 0.002, value=5e8, days=300)
    got = look(db, screen_rate={"rate": 0.61, "n": 800})
    assert got["rate"] == 0.61 and got["n"] == 800 and got["limited"] is False


def test_a_liquid_stock_off_every_list_has_no_risk_line(db):
    series(db, "HELD", 0.002, value=5e8, days=300)
    assert look(db)["risk_line"] is None


def test_under_200_days_of_history_is_limited_evidence_with_no_cases(db):
    series(db, "HELD", 0.002, value=5e8, days=20)               # a new listing
    got = look(db)
    assert got["limited"] is True and got["n"] == 0 and got["rate"] == 0.5


def test_a_stock_with_no_prices_at_all_is_limited_evidence(db):
    got = look(db, symbol="NOPRICES")
    assert got["limited"] is True and got["n"] == 0


def test_under_30_cases_in_the_bucket_is_limited_evidence(db):
    series(db, "HELD", 0.002, value=5e8, days=300)
    thin = {k: {"n": 12, "hit_rate": v["hit_rate"]} for k, v in RATES.items()}
    got = look(db, rates=thin)
    assert got["n"] == 12 and got["limited"] is True


def test_the_screen_is_not_consulted_for_a_stock_it_already_scored(db):
    """A held stock that is on the screen keeps the screen's own number; this lookup is only for the rest."""
    series(db, "HELD", 0.002, value=5e8, days=300)
    assert hb.needs_own_history("HELD", {"HELD": {}}) is False
    assert hb.needs_own_history("OTHER", {"HELD": {}}) is True
