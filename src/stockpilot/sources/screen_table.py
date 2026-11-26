"""The universe table the screener screen loads once: every stock in the search index with its sector, P/E, profit
growth, our 6-month chance (the nightly mechanical result), size and last price. Columns, not rows, so 9,000 stocks
stay small. Public market data only. Shape: `universe_table` in schemas/live-contract.json."""
import json
import sys
from pathlib import Path

# column -> where it comes from; every column has one value per stock, null when we do not have it
COLUMNS = ("symbol", "exchange", "segment", "name", "sector", "pe", "growth", "chance_6m", "mcap_cr", "last", "day_change_pct")


def _get(d, *path):
    for p in path:
        d = d.get(p) if isinstance(d, dict) else None
    return d


def build_table(index: dict, facts: dict, mech: dict, built_at: str) -> dict:
    """facts: {(symbol, exchange): stock-facts doc}; mech: the mechanical results file."""
    chance = {(r["symbol"], r["exchange"]): r.get("chance_6m") for r in mech.get("results", [])}
    out = {c: [] for c in COLUMNS}
    for e in index["entries"]:
        key = (e["symbol"], e["exchange"]); f = facts.get(key) or {}
        row = {"symbol": e["symbol"], "exchange": e["exchange"], "segment": e["segment"], "name": e["name"],
               "sector": f.get("sector"), "pe": _get(f, "valuation", "pe"), "growth": _get(f, "quality", "profit_growth_yoy_pct"),
               "chance_6m": chance.get(key), "mcap_cr": _get(f, "valuation", "market_cap_cr"),
               "last": _get(f, "today", "last"), "day_change_pct": _get(f, "today", "day_change_pct")}
        for c in COLUMNS:
            out[c].append(row[c])
    return {"built_at": built_at, "n": len(index["entries"]), **out}


def main(argv=None):
    """python -m stockpilot.sources.screen_table INDEX.json FACTS_DIR MECH.json OUT.json"""
    from datetime import datetime, timedelta, timezone
    index_p, facts_dir, mech_p, out_p = (Path(a) for a in (argv or sys.argv[1:]))
    index = json.loads(index_p.read_text()); mech = json.loads(mech_p.read_text()) if mech_p.exists() else {"results": []}
    facts = {}
    for e in index["entries"]:
        p = facts_dir / f"{e['symbol']}.json"
        if p.exists():
            d = json.loads(p.read_text())
            facts[(d.get("symbol", e["symbol"]), d.get("exchange", e["exchange"]))] = d
    now = datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(timespec="seconds")
    t = build_table(index, facts, mech, now)
    out_p.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_p.with_suffix(".tmp"); tmp.write_text(json.dumps(t, separators=(",", ":"), ensure_ascii=False)); tmp.replace(out_p)
    print(f"universe table: {t['n']} stocks, {sum(v is not None for v in t['pe'])} with P/E, {sum(v is not None for v in t['chance_6m'])} with a chance")


if __name__ == "__main__":
    main()
