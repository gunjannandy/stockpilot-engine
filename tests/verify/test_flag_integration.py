"""A flagged price series is hidden from the site and left out of the calls (check 3's promise)."""
import json
import shutil
from datetime import date, datetime

import pytest

from vhelpers import DAY, price_rows
from helpers import insert_prices
from stockpilot import forecast, site, store
from stockpilot.verify import flags

from test_forecast import AS_OF, RULES, fake_analyse, template  # noqa: F401  (the seeded forecast store, built once)


def _small(tmp_path):
    db = store.open(tmp_path / "s.duckdb")
    for sym, closes in {"GOOD": [100.0 + i * 0.1 for i in range(260)], "BROKEN": [100.0] * 230 + [20.0] * 30}.items():
        insert_prices(db, price_rows(sym, closes))
        db.execute("insert into stocks values (?, ?, 'X', ?)", [sym, f"{sym} Ltd", "INE" + sym])
        db.execute("insert into holdings values ('2026-11-20 18:00:00', 'equity', ?, ?, 10, 50, 'kite')", [sym, "INE" + sym])
        db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, source) values "
                   "('stock', ?, ?, '2024-01-02', 10, 50, 'tradebook')", [sym, "INE" + sym])
    return db


def test_a_flagged_holding_shows_no_gain_and_no_chart(tmp_path):
    db = _small(tmp_path)
    flags.sync(db, DAY)
    out = tmp_path / "site"
    site.build(db, out, today=DAY, now=datetime(2026, 11, 20, 19, 30))
    holdings = {h["symbol"]: h for h in json.loads((out / "data" / "portfolio.json").read_text())["holdings"]}
    assert holdings["BROKEN"]["gain_pct"] is None and holdings["BROKEN"]["quantity"] == 10     # still owned, just no gain
    assert holdings["GOOD"]["gain_pct"] is not None
    assert not (out / "data" / "history" / "BROKEN.json").exists() and (out / "data" / "history" / "GOOD.json").exists()
    assert "BROKEN" not in {s["symbol"] for s in json.loads((out / "data" / "search.json").read_text())}


def test_the_forecast_leaves_a_flagged_holding_out_of_the_brief_and_the_calls(template, tmp_path):   # noqa: F811
    shutil.copy(template, tmp_path / "t.duckdb")
    db = store.open(tmp_path / "t.duckdb")
    seen = []
    first = forecast.run(db, AS_OF, fake_analyse(seen=seen), ["fake"], RULES, 100000.0)
    held = {s["symbol"] for s in seen[0][1]["stocks"]}
    assert "INFY" in held and first["status"] == "ok"
    db.execute("insert into price_flags values ('INFY', '2026-10-01', -0.8, 'split_like', 100, 20, ?)", [AS_OF])
    db.execute("delete from calls where made_on = ?", [AS_OF])
    seen.clear()
    out = forecast.run(db, AS_OF, fake_analyse(seen=seen), ["fake"], RULES, 100000.0)
    assert out["status"] == "ok" and "INFY" not in {s["symbol"] for s in seen[0][1]["stocks"]}
    assert db.execute("select count(*) from calls where made_on = ? and symbol = 'INFY'", [AS_OF]).fetchone()[0] == 0
    assert db.execute("select count(*) from problems where message like 'INFY: its price series%'").fetchone()[0] == 1
