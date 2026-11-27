"""Check 3's machinery: unexplained jumps over 40% inside the window flag a series; a corporate action explains one away;
the screen skips a flagged series."""
from datetime import date, timedelta

from vhelpers import DAY, bdays, price_rows
from helpers import insert_prices
from stockpilot.verify import flags


def _jump_series(db, symbol, factor=0.2, at=-30, n=120):
    closes = [100.0] * (n + at) + [100.0 * factor] * (-at)
    insert_prices(db, price_rows(symbol, closes))
    db.execute("insert into stocks values (?, ?, 'X', ?)", [symbol, symbol, "INE" + symbol])
    return bdays(DAY, n)[n + at]


def test_unexplained_drop_is_flagged_and_explained_one_is_not(db):
    when = _jump_series(db, "BROKEN")
    _jump_series(db, "SPLITOK")
    db.execute("insert into corporate_actions (symbol, ex_date, kind, numerator, denominator, source) "
               "values ('SPLITOK', ?, 'split', 5, 1, 'nse')", [bdays(DAY, 120)[90]])
    found = flags.scan(db, DAY)
    assert [(f.symbol, f.jump_date) for f in found] == [("BROKEN", when)]
    assert found[0].kind == "split_like"          # 100 -> 20 is a 1:5 drop that stays down: probably a missing split


def test_old_jump_outside_the_window_and_penny_ticks_are_not_flagged(db):
    insert_prices(db, price_rows("OLD", [100.0] * 40 + [20.0] * 740, end=DAY))        # the jump is ~3 years back
    insert_prices(db, price_rows("PENNY", [0.10] * 60 + [0.15] * 60))                  # one tick is 50% on a 10 paise stock
    assert flags.scan(db, DAY) == []


def test_a_bad_tick_that_reverts_is_called_a_bad_tick(db):
    closes = [100.0] * 60 + [30.0] + [100.0] * 60
    insert_prices(db, price_rows("TICK", closes))
    got = flags.scan(db, DAY)
    assert {f.kind for f in got} == {"bad_tick"} and len(got) == 2        # the drop and the snap back


def test_sync_stores_then_clears_when_an_action_explains_it(db):
    _jump_series(db, "BROKEN")
    assert [f.symbol for f in flags.sync(db, DAY)] == ["BROKEN"]
    assert flags.flagged_symbols(db) == {"BROKEN"}
    db.execute("insert into corporate_actions (symbol, ex_date, kind, numerator, denominator, source) "
               "values ('BROKEN', ?, 'split', 5, 1, 'nse')", [bdays(DAY, 120)[90]])
    flags.sync(db, DAY)
    assert flags.flagged_symbols(db) == set()


def test_screen_skips_a_flagged_series_even_on_the_watchlist(db):
    from stockpilot.analysis import screen
    for sym in ("GOOD1", "GOOD2", "GOOD3", "BROKEN"):
        insert_prices(db, price_rows(sym, [100.0 + i * 0.1 for i in range(260)]) if sym != "BROKEN"
                      else price_rows(sym, [100.0] * 230 + [20.0] * 30, end=DAY))
        db.execute("insert into stocks values (?, ?, 'X', ?)", [sym, sym, "INE" + sym])
    db.execute("insert into watchlist (symbol, exchange, added_by) values ('BROKEN', 'NSE', 'owner')")
    flags.sync(db, DAY)
    result = screen.run(db, DAY, 1.0, fresh=True)
    assert "BROKEN" not in {c["symbol"] for c in result["candidates"]}
    assert "price series" in result["excluded"]["BROKEN"]
