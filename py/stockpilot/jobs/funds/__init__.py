"""The funds Job (decisions §2 Schedules): public data only, run from GitHub Actions.

Reads AMFI's scheme list (category, house, today's NAV), AMFI's cost tables (TER, size) and mfapi.in's NAV
history per scheme, and publishes the `funds` dataset: one row per fund (its Direct Growth scheme) with returns,
the category's middle returns, worst fall, rolling returns and weekly NAVs. The Funds screen reads it through
the Worker's /api/funds routes. A fund whose NAV history cannot be read is left out; the run goes on.
"""
import json
import time
from collections.abc import Callable
from datetime import date, datetime, timedelta
from statistics import median

from stockpilot.sources import fund_stats, fund_universe

KIND = "funds"
DATASET = "funds"
MFAPI_URL = "https://api.mfapi.in/mf/{code}"
LIMIT = 900                 # contract FUNDS_MAX: the door takes 1,000 rows a day
YEARS = 5
PAUSE_S = 0.4               # between mfapi.in calls
MIN_CATEGORY = fund_stats.MIN_CATEGORY
# Which kinds of fund come first when the cap bites; inside a kind, the biggest funds first.
KIND_ORDER = ("Equity Scheme", "Hybrid Scheme", "Other Scheme", "Solution Oriented Scheme", "Debt Scheme")


def universe(schemes: list[dict]) -> list[dict]:
    """Funds whose primary scheme is a live Direct Growth plan, with today's NAV."""
    by_code = {s["code"]: s for s in schemes}
    out = []
    for f in fund_universe.group_funds(schemes):
        p = next(v for v in f["variants"] if v["code"] == f["primary_code"])
        if p["plan"] == "Direct" and p["option"] == "Growth" and p["nav"]:
            f["nav"], f["nav_date"] = p["nav"], p["day"]
            f["amc"] = f["amc"] or by_code[p["code"]]["amc"]
            out.append(f)
    return out


def _rank(f: dict) -> tuple:
    cat = f.get("category") or ""
    kind = next((i for i, k in enumerate(KIND_ORDER) if cat.startswith(k)), len(KIND_ORDER))
    return (kind, -(f.get("aum_cr") or 0), f["id"])


def choose(funds: list[dict], limit: int = LIMIT) -> list[dict]:
    return sorted(funds, key=_rank)[:limit]


def weekly(series: list[tuple[str, float]], today: date, years: int = YEARS) -> list[dict]:
    """[{"d": day, "v": NAV}] oldest first: the last NAV of each week over `years` years, zero NAVs skipped."""
    floor = str(today - timedelta(days=365 * years + 7))
    last: dict[tuple, tuple[str, float]] = {}
    for day, v in sorted(series):
        if v and v > 0 and day >= floor:
            iso = date.fromisoformat(day).isocalendar()
            last[(iso[0], iso[1])] = (day, v)
    return [{"d": d, "v": v} for d, v in sorted(last.values())]


def max_fall(navs: list[dict]) -> float | None:
    """Worst fall from a peak to a later low, percent (negative)."""
    peak, worst = None, 0.0
    for n in navs:
        v = n["v"]
        peak = v if peak is None or v > peak else peak
        worst = min(worst, (v / peak - 1) * 100)
    return round(worst, 2) if peak else None


def stats(navs: list[dict]) -> dict:
    ends = fund_stats.month_ends([(n["d"], n["v"]) for n in navs])
    roll = list(fund_stats._roll1y(ends).values())
    return {
        "r1": fund_stats.yearly(ends, 1), "r3": fund_stats.yearly(ends, 3), "r5": fund_stats.yearly(ends, 5),
        "max_fall": max_fall(navs),
        "roll_min": round(min(roll), 2) if roll else None,
        "roll_median": round(median(roll), 2) if roll else None,
        "roll_max": round(max(roll), 2) if roll else None,
        "roll_loss_share": round(sum(r < 0 for r in roll) / len(roll), 3) if roll else None,
    }


def with_categories(rows: list[dict]) -> None:
    """Add the category's middle 1, 3 and 5 year returns (only for categories of at least MIN_CATEGORY funds)."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        if r["category"]:
            groups.setdefault(r["category"], []).append(r)
    for r in rows:
        members = groups.get(r["category"] or "", [])
        big = len(members) >= MIN_CATEGORY
        r["category_n"] = len(members)
        for k in ("r1", "r3", "r5"):
            vals = [m[k] for m in members if m[k] is not None]
            r[f"cat_{k}"] = round(median(vals), 2) if big and vals else None


def parse_mfapi(doc: dict) -> list[tuple[str, float]]:
    """[(YYYY-MM-DD, NAV)] from mfapi.in's {"data": [{"date": "dd-mm-yyyy", "nav": "12.3"}]}."""
    out = []
    for p in doc.get("data") or []:
        try:
            out.append((datetime.strptime(p["date"], "%d-%m-%Y").date().isoformat(), float(p["nav"])))
        except (KeyError, ValueError):
            continue
    return out


def build_row(f: dict, series: list[tuple[str, float]], today: date) -> dict | None:
    navs = weekly(series, today)
    if len(navs) < 2:
        return None
    return {
        "id": f["id"], "code": f["primary_code"], "name": f["name"], "amc": f["amc"], "category": f["category"],
        "nav": f["nav"], "nav_date": str(f["nav_date"]) if f.get("nav_date") else None,
        "ter": f.get("ter_direct"), "ter_regular": f.get("ter_regular"), "aum_cr": f.get("aum_cr"),
        **stats(navs), "navs_json": json.dumps([[n["d"], n["v"]] for n in navs], separators=(",", ":")),
    }


def collect(today: date, fetch: Callable[[str], bytes | None], sleep: Callable[[float], None] = time.sleep,
            progress: Callable[[str], None] = lambda _: None) -> list[dict]:
    blob = fetch(fund_universe.NAVALL_URL)
    if not blob:
        raise RuntimeError("AMFI's scheme list did not answer")
    funds = universe(fund_universe.parse_navall(blob))
    try:
        ter, aum = fund_universe.fetch_costs(fetch, today)
        fund_universe.attach_costs(funds, ter, aum)
    except Exception as err:  # noqa: BLE001 - costs are a bonus: no cost is better than no fund
        progress(f"costs not read: {err!r}")
    rows, failed = [], 0
    for f in choose(funds):
        try:
            doc = json.loads(fetch(MFAPI_URL.format(code=f["primary_code"])) or b"{}")
        except Exception:  # noqa: BLE001 - one fund failing leaves only that fund out
            failed += 1
            continue
        finally:
            sleep(PAUSE_S)
        row = build_row(f, parse_mfapi(doc), today)
        if row:
            rows.append(row)
    progress(f"read {len(rows)} funds, {failed} NAV histories failed")
    with_categories(rows)
    return rows


def run(ctx, fetch: Callable[[str], bytes | None] | None = None) -> str:
    if fetch is None:
        from stockpilot.sources.http import fetch as http_fetch

        fetch = http_fetch
    day = ctx.range.end
    rows = collect(day, fetch, progress=ctx.progress.line)
    ctx.publish(DATASET, rows, source="amfi+mfapi", as_of=str(day))
    return f"published {len(rows)} funds"
