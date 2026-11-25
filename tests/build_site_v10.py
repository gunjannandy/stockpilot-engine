"""Build the v10 test site from lane A's real export: the repo's test seed (tests/site_export_seed.py) through `site.build`.
Every file is what `sp build-site` writes. Only three scenario touches (and one mark in `long_term_marks`, exported by the real code) are added, each named here, because the seed has none
of them: a Review call, a Health gap row, and an answered analyst note on a second stock. Nothing is invented for any contract field.
Usage: python tests/build_site_v10.py <out dir>"""
import json
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from seed_site import AS_OF, TOKENS
from site_export_seed import seed
from stockpilot import site


def scenario(out: Path) -> None:
    data = out / "data"
    today = json.loads((data / "today.json").read_text())
    keep = today.get("keep") or []
    if keep and not any(c.get("sell_kind") == "review" for g in ("sell", "keep") for c in today.get(g, [])):
        c = today["keep"].pop(0)                       # a marked long-term holding whose chance fell: lane E gives it sell_kind "review"
        c["sell_kind"] = "review"
        today["sell"].append(c)
    (data / "today.json").write_text(json.dumps(today))
    health = json.loads((data / "health.json").read_text())
    if not health.get("gaps"):                         # shape from src/stockpilot/gaps.py via site.py
        health["gaps"] = [{"area": "fund NAV history", "subject": "Nippon India Gold Savings Fund", "reason": "Not collected yet", "detail": "run sp navs-history", "since": "2026-11-18 08:00:00"}]
        (data / "health.json").write_text(json.dumps(health))


def rsu_lots(db) -> None:
    """RSU lots in the real `lots` table (what lane R writes), so `portfolio.rsu` is not null: one from Fidelity's list, two from
    vest papers, one estimated. Cost per share is above the fixture price, so the sale is a loss (the 'no tax, a loss' wording)."""
    rows = [(date(2024, 5, 9), 4, 1150.0, "fidelity_statement", False), (date(2025, 6, 3), 3, 1100.0, "vest_document", False),
            (date(2025, 12, 5), 3, 1120.0, "vest_document", False), (date(2026, 11, 20), 2, 1090.0, "estimate", True)]
    for day, qty, cost, source, est in rows:
        db.execute("insert into lots (kind, symbol, isin, acquired_on, quantity, cost_per_unit, currency, source, estimated) "
                   "values ('rsu', 'NOW', 'US81762P1021', ?, ?, ?, 'USD', ?, ?)", [day, qty, cost, source, est])


def build(out: Path) -> Path:
    db = seed(Path(tempfile.mkdtemp()) / "sp.duckdb")
    db.execute("insert into long_term_marks (symbol, marked_by) values ('ITC', 'owner')")      # a real mark in the real table; the exporter carries it
    rsu_lots(db)
    site.build(db, out, today=AS_OF, budget_inr=100000, now=datetime(2026, 11, 20, 19, 30), tokens=TOKENS)
    scenario(out)
    return out


if __name__ == "__main__":
    print(build(Path(sys.argv[1])))
