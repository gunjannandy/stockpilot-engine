"""Seam 2: what `sp weekly` computes is what the dashboard shows."""
import json
from datetime import date

from seed_site import AS_OF, seed

from stockpilot import site, vmqueue, weekly

SAT = date(2026, 11, 21)


def build(tmp_path, target=None):
    db = seed(tmp_path / "sp.duckdb")
    db.execute("delete from weekly_reports")
    db.execute("delete from holdings where symbol not in ('INFY', 'WIPRO', 'TATAMOTORS', 'Parag Parikh Flexi Cap Fund')")   # the weekly seam is about one fund
    db.execute("insert into holdings values (?, 'stock', 'ITC', 'INE154A01025', 100, 400, 'kite')",
               [__import__("datetime").datetime(2026, 11, 20, 18, 0)])
    weekly.run(db, SAT, tmp_path / "pack", target=target, private={"slab_income": 1_500_000})
    site.build(db, tmp_path / "site", today=AS_OF, pack_dir=tmp_path / "pack")
    return db, json.loads((tmp_path / "site" / "data" / "portfolio.json").read_text())


def test_weekly_sections_reach_the_portfolio_page(tmp_path):
    _, page = build(tmp_path, target={"stocks": 0.6, "equity_funds": 0.4})
    assert [f["verdict"] for f in page["funds"]] == ["Too early to judge"]       # the one fund held
    assert page["opportunities"] and set(page["opportunities"][0]) == {"name", "why"}
    assert page["opportunities"][0]["name"] != page["opportunities"][0]["name"].upper()   # a name, not a ticker
    assert page["tax"]["fy"] == "2026-27" and page["tax"]["notes"]
    assert page["tax"]["harvest_room"] == 125000          # nothing sold: the whole free allowance is open
    assert page["allocation"]["proposed"] == {"stocks": 0.6, "equity_funds": 0.4}
    assert page["allocation"]["approved"] is False


def test_the_tax_pack_is_zipped_into_the_site_and_linked(tmp_path):
    _, page = build(tmp_path)
    link = page["tax"]["itr_pack"]
    assert link == "downloads/tax-pack-2026-27.zip"
    assert (tmp_path / "site" / link).exists()


def test_holdings_from_kite_are_stocks_on_the_page(tmp_path):
    _, page = build(tmp_path)
    itc = next(h for h in page["holdings"] if h["symbol"] == "ITC")
    assert itc["kind"] == "equity" and itc["group"] == "Indian stocks"
    assert "stocks" in page["allocation"]["current"]
    assert page["allocation"]["labels"]["stocks"] == "Indian stocks"


def test_an_approved_target_is_shown_as_approved_even_when_dashboard_wrapped_it(tmp_path):
    db, _ = build(tmp_path)
    target = {"stocks": 0.6, "equity_funds": 0.4}
    vmqueue._allocation_approve(db, {"target": target}, "father")     # the page posts {target: ...}
    weekly.run(db, SAT, tmp_path / "pack", target=target)
    site.build(db, tmp_path / "site", today=AS_OF, pack_dir=tmp_path / "pack")
    page = json.loads((tmp_path / "site" / "data" / "portfolio.json").read_text())
    assert page["allocation"]["target"] == target and page["allocation"]["approved"] is True
    assert page["allocation"]["proposed"] is None
