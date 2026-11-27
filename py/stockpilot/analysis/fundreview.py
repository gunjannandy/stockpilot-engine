"""Weekly fund review: each fund held, ranked against the other funds in its category on 3-year return.
Past return is one signal, not a verdict, so the wording says 'Review', never 'Sell'."""
from datetime import date, timedelta
from statistics import median

import duckdb

from stockpilot.book import positions
from stockpilot import valuation
from stockpilot.sources import fundcosts

MIN_PEERS = 4
YEAR = 365


def _nav_on(db, code: int, day: date):
    row = db.execute("select nav from navs where scheme_code = ? and date <= ? and date >= ? order by date desc limit 1",
                     [code, day, day - timedelta(days=10)]).fetchone()
    return row[0] if row else None


def _cagr(now, then, years):
    return (now / then) ** (1 / years) - 1 if now and then else None


def _returns(db, code, as_of):
    now = _nav_on(db, code, as_of)
    return {"ret_1y": _cagr(now, _nav_on(db, code, as_of - timedelta(days=YEAR)), 1),
            "ret_3y": _cagr(now, _nav_on(db, code, as_of - timedelta(days=3 * YEAR)), 3)}


def review(db: duckdb.DuckDBPyConnection, as_of: date) -> list[dict]:
    out = []
    for h in ({"symbol": p.name, "isin": p.isin} for p in positions.held(db, as_of) if p.kind == "mf"):
        fund = valuation.fund_for(db, h["isin"])
        if not fund:
            out.append({"name": h["symbol"], "isin": h["isin"], "verdict": "Too early to judge", "rank": None,
                        "why": "This fund is not in the AMFI list, so it cannot be compared.", "better_peer": None,
                        "ter": None, "aum_cr": None, "flags": []})
            continue
        code, name, plan, option, category = fund
        mine = _returns(db, code, as_of)
        costs = fundcosts.lookup(db, name, plan)
        row = {"name": name, "isin": h["isin"], "category": category, **mine, "rank": None, "median_3y": None,
               "better_peer": None, "note": "", "ter": costs and costs["ter"], "aum_cr": costs and costs["aum_cr"],
               "flags": ["small"] if fundcosts.is_small(costs) else []}
        # NAV returns are already after the fund's own TER, so ranking on them is ranking on return net of cost.
        if (plan or "").lower().startswith("regular"):
            row["note"] = "This is a Regular plan. The Direct plan of the same fund costs less each year."
            both = fundcosts.both_ters(db, name)
            if both and both[0] is not None and both[1] is not None:
                row["note"] += f" Regular costs {both[0]:.2f}% a year, Direct {both[1]:.2f}%."
        peers, small_peers = {}, set()
        for pcode, pname in db.execute(
                "select scheme_code, name from funds where category = ? and plan like 'Direct%' "
                "and option like '%Growth%' and scheme_code <> ?", [category, code]).fetchall():
            r = _returns(db, pcode, as_of)["ret_3y"]
            if r is not None:
                peers[pname] = r
                small_peers.update([pname] if fundcosts.is_small(fundcosts.lookup(db, pname, "Direct")) else [])
        if mine["ret_3y"] is None:
            row |= {"verdict": "Too early to judge", "why": "Fewer than 3 years of prices on file for this fund."}
        elif len(peers) + 1 < MIN_PEERS:
            row |= {"verdict": "Too early to judge",
                    "why": f"Only {len(peers) + 1} peers with 3 years of history in {category}; need {MIN_PEERS}."}
        else:
            field = {**peers, name: mine["ret_3y"]}
            ordered = sorted(field.items(), key=lambda kv: -kv[1])
            rank = [n for n, _ in ordered].index(name) + 1
            n = len(ordered)
            row["rank"], row["median_3y"] = (rank, n), median(field.values())
            if rank > n * 0.75:
                best = next((kv for kv in ordered if kv[0] not in small_peers), ordered[0])     # never point to a fund under Rs 500 cr
                row |= {"verdict": "Review", "better_peer": best[0],
                        "why": f"In the bottom quarter of its category over 3 years: {mine['ret_3y']:.1%} a year, "
                               f"{rank} of {n}. The best peer, {best[0]}, made {best[1]:.1%}."}
            else:
                row |= {"verdict": "Keep", "why": f"{rank} of {n} in its category over 3 years "
                                                  f"({mine['ret_3y']:.1%} a year against a middle of {row['median_3y']:.1%})."}
        if row["flags"]:
            row["why"] += (f" Small fund: about ₹{row['aum_cr']:,.0f} crore of assets, under ₹{fundcosts.SMALL_AUM_CR} crore, "
                           "so it can be merged or closed.")
        out.append(row)
    return out
