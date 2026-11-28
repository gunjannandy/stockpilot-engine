"""The weekly fund call (public part): from the weekly NAVs the funds Job already holds, each fund is screened
against its category and given Buy, Watch or nothing. The chance behind a call is a measured base rate: at past
checkpoints, how often funds in the same kind and 3-year quartile beat their category's middle fund over the next
12 months. Too few cases and no rate is given, never a made-up one. Held funds are matched privately on the VM,
never here. Nothing here touches an order endpoint."""
import json
import math
from datetime import date
from statistics import median

HORIZON_MONTHS = 12
STEP_MONTHS = 3
MIN_PEERS = 5
MIN_N, MIN_PERIODS = 30, 4
BUY_PCT, WATCH_PCT = 0.25, 0.50          # 3-year rank as a share of the category
BUY_MAX_LOSS_SHARE = 0.15                # at most this share of rolling years below zero
MIN_AUM_CR = 500.0
CAVEAT = ("Only funds alive today are on file, so closed and merged funds are missing and every rate is a little "
          "flattering. Checks overlap, so the case count overstates the evidence.")


def group_of(category: str | None) -> str:
    return (category or "Other").split(" - ")[0].strip()


def _month(day: str) -> int:
    d = date.fromisoformat(day)
    return d.year * 12 + d.month - 1


def month_grid(navs: list) -> dict[int, float]:
    """{month number: last NAV in that month} from [[day, nav], ...]."""
    out: dict[int, float] = {}
    for day, v in sorted(navs):
        if v and v > 0:
            out[_month(day)] = v
    return out


def _navs(row: dict) -> list:
    try:
        return json.loads(row.get("navs_json") or "[]")
    except ValueError:
        return []


def base_rates(rows: list[dict]) -> dict[tuple[str, int], dict]:
    """{(group, quartile): {n, periods, hit_rate, avg_excess}} over past quarter-end checkpoints."""
    cats: dict[str, dict[str, dict[int, float]]] = {}
    for r in rows:
        if r.get("category"):
            g = month_grid(_navs(r))
            if g:
                cats.setdefault(r["category"], {})[r["id"]] = g
    tally: dict[tuple[str, int], dict] = {}
    for category, grids in cats.items():
        if len(grids) < MIN_PEERS:
            continue
        first, last = min(min(g) for g in grids.values()), max(max(g) for g in grids.values())
        t = last - HORIZON_MONTHS
        while t - 36 >= first:
            r3 = {c: (g[t] / g[t - 36]) ** (1 / 3) - 1 for c, g in grids.items() if t in g and t - 36 in g}
            ahead = {c: g[t + HORIZON_MONTHS] / g[t] - 1 for c, g in grids.items()
                     if t in g and t + HORIZON_MONTHS in g}
            both = [c for c in r3 if c in ahead]
            if len(both) >= MIN_PEERS:
                middle = median(ahead[c] for c in both)
                for rank, c in enumerate(sorted(both, key=lambda c: -r3[c]), start=1):
                    q = tally.setdefault((group_of(category), math.ceil(4 * rank / len(both))),
                                         {"n": 0, "hits": 0, "excess": 0.0, "periods": set()})
                    q["n"] += 1
                    q["hits"] += ahead[c] > middle
                    q["excess"] += ahead[c] - middle
                    q["periods"].add(t)
            t -= STEP_MONTHS
    return {k: {"n": q["n"], "periods": len(q["periods"]), "hit_rate": q["hits"] / q["n"],
                "avg_excess": q["excess"] / q["n"]} for k, q in tally.items()}


def rate_for(rates: dict, category: str | None, quartile: int) -> dict | None:
    r = rates.get((group_of(category), quartile))
    return r if r and r["n"] >= MIN_N and r["periods"] >= MIN_PERIODS else None


def screen(rows: list[dict]) -> list[dict]:
    """[{row, call, quartile, rank, reasons}] for funds worth a Buy or a Watch. Needs 5+ funds with a 3-year return."""
    by_cat: dict[str, list[dict]] = {}
    for r in rows:
        if r.get("category") and r.get("r3") is not None:
            by_cat.setdefault(r["category"], []).append(r)
    out = []
    for peers in by_cat.values():
        if len(peers) < MIN_PEERS:
            continue
        ordered = sorted(peers, key=lambda r: (-r["r3"], r["id"]))
        n = len(ordered)
        for rank, r in enumerate(ordered, start=1):
            share, reasons = rank / n, []
            if share > WATCH_PCT:
                continue
            ok = True
            if r.get("r1") is None or r.get("cat_r1") is None or r["r1"] < r["cat_r1"]:
                ok = False
                reasons.append("last year's return is below the category's middle")
            if r.get("roll_loss_share") is None or r["roll_loss_share"] > BUY_MAX_LOSS_SHARE:
                ok = False
                reasons.append("too many rolling years lost money")
            if (r.get("aum_cr") or 0) < MIN_AUM_CR:
                ok = False
                reasons.append("size is small or unknown")
            if r.get("ter") is None:
                ok = False
                reasons.append("cost is unknown")
            call = "buy" if share <= BUY_PCT and ok else "watch"
            if call == "watch" and share > BUY_PCT:
                reasons.insert(0, "in the top half of its category on 3 years, not the top quarter")
            out.append({"row": r, "call": call, "quartile": math.ceil(4 * rank / n), "rank": rank, "of": n,
                        "reasons": reasons})
    return out


def build(rows: list[dict], as_of: str) -> list[dict]:
    """The `fund_calls` rows: one per called fund (id = fund id), one per measured track-record cell (id = track:...)."""
    rates = base_rates(rows)
    out = []
    for s in screen(rows):
        r = s["row"]
        rate = rate_for(rates, r["category"], s["quartile"])
        out.append({
            "id": r["id"], "kind": "call", "name": r["name"], "category": r["category"], "call": s["call"],
            "rank": s["rank"], "of": s["of"], "quartile": s["quartile"],
            "chance": round(rate["hit_rate"], 3) if rate else None,
            "cases": rate["n"] if rate else None, "periods": rate["periods"] if rate else None,
            "avg_excess": round(rate["avg_excess"] * 100, 2) if rate else None,
            "reasons": "; ".join(s["reasons"]),
            "caveat": CAVEAT, "as_of": as_of,
        })
    for (group, q), v in sorted(rates.items()):
        out.append({
            "id": f"track:{group}:{q}", "kind": "track", "name": group, "category": group, "call": None,
            "rank": None, "of": None, "quartile": q, "chance": round(v["hit_rate"], 3), "cases": v["n"],
            "periods": v["periods"], "avg_excess": round(v["avg_excess"] * 100, 2), "reasons": "",
            "caveat": CAVEAT, "as_of": as_of,
        })
    return out


# ---- held funds (the caller passes the held ids; nothing about holdings is stored or published here) ----

def held_calls(rows: list[dict], held_ids: list[str], as_of: str) -> list[dict]:
    """One call per held fund found in rows: Add (the screen would Buy it), Keep (top half of its category),
    Review (bottom half, last year below the category and rolling years lost), or No data. The chance is the same
    measured base rate by kind and quartile, None when the cases are too few."""
    rates = base_rates(rows)
    screened = {s["row"]["id"]: s for s in screen(rows)}
    by_id = {r["id"]: r for r in rows}
    out = []
    for fid in held_ids:
        r = by_id.get(fid)
        if r is None or r.get("r3") is None or not r.get("category"):
            out.append({"id": fid, "call": "No data", "chance": None, "cases": None,
                        "reasons": "not enough NAV history or category peers", "as_of": as_of})
            continue
        s = screened.get(fid)
        peers = [p["r3"] for p in rows if p.get("category") == r["category"] and p.get("r3") is not None]
        rank = 1 + sum(v > r["r3"] for v in peers)
        quartile = math.ceil(4 * rank / len(peers))
        if s and s["call"] == "buy":
            call, why = "Add", "top quarter of its category on 3 years and nothing weak"
        elif s:
            call, why = "Keep", "; ".join(s["reasons"]) or "top half of its category on 3 years"
        elif r.get("r1") is not None and r.get("cat_r1") is not None and r["r1"] < r["cat_r1"] \
                and (r.get("roll_loss_share") or 0) > BUY_MAX_LOSS_SHARE:
            call, why = "Review", "bottom half on 3 years, below the category last year, and rolling years lost money"
        else:
            call, why = "Keep", "bottom half on 3 years but no other weakness"
        rate = rate_for(rates, r["category"], quartile)
        out.append({"id": fid, "call": call, "quartile": quartile,
                    "chance": round(rate["hit_rate"], 3) if rate else None,
                    "cases": rate["n"] if rate else None, "reasons": why, "caveat": CAVEAT, "as_of": as_of})
    return out


def score_calls(past: list[dict], rows: list[dict], today: str) -> dict:
    """Score earlier published calls once 12 months have passed: did the fund beat its category's middle fund over the
    year after the call? past rows need id, call, as_of. Returns {call: {n, hits, hit_rate}}; unscored ones are left out."""
    grids = {r["id"]: month_grid(_navs(r)) for r in rows}
    cat_of = {r["id"]: r.get("category") for r in rows}
    t_now = _month(today)
    tally: dict[str, dict] = {}
    for p in past:
        t = _month(p["as_of"])
        grid = grids.get(p["id"], {})
        if not p.get("call") or t + HORIZON_MONTHS > t_now or t not in grid or t + HORIZON_MONTHS not in grid:
            continue
        peers = [g for fid, g in grids.items()
                 if cat_of[fid] == cat_of[p["id"]] and t in g and t + HORIZON_MONTHS in g]
        if len(peers) < MIN_PEERS:
            continue
        middle = median(g[t + HORIZON_MONTHS] / g[t] - 1 for g in peers)
        q = tally.setdefault(p["call"], {"n": 0, "hits": 0})
        q["n"] += 1
        q["hits"] += grid[t + HORIZON_MONTHS] / grid[t] - 1 > middle
    return {k: {"n": v["n"], "hits": v["hits"], "hit_rate": v["hits"] / v["n"]} for k, v in tally.items()}
