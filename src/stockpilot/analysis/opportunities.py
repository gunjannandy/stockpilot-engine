"""Weekly opportunities: the best screened stocks the owners do not hold yet, each with the one reason it ranks high."""
from datetime import date

import duckdb

from stockpilot.book import positions
from stockpilot.analysis import screen

STRENGTH = {"quality": "strong business quality", "value": "cheap against its sector",
            "momentum": "price trend is strong", "risk": "steady price, small falls"}


def pick(candidates: list[dict], held: set[str], n: int = 10) -> list[dict]:
    out = []
    for c in sorted(candidates, key=lambda c: c["composite"], reverse=True):
        if c["symbol"] in held or c["flags"]:
            continue
        factor, score = max(c["scores"].items(), key=lambda kv: kv[1])
        out.append({"symbol": c["symbol"], "industry": c["industry"], "composite": c["composite"],
                    "watchlist": c.get("watchlist", False),
                    "why": f"{STRENGTH[factor].capitalize()}: better than {score:.0%} of its sector peers."})
        if len(out) == n:
            break
    return out


def weekly(db: duckdb.DuckDBPyConnection, as_of: date, liquidity_floor_cr: float = 1.0, n: int = 10) -> dict:
    result = screen.run(db, as_of, liquidity_floor_cr)
    held = {p.symbol for p in positions.held(db, as_of)}
    return {"as_of": as_of, "picks": pick(result["candidates"], held, n), "health": result["health"]}
