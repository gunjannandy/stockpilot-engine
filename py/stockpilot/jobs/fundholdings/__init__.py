"""The fund-holdings Job: each of the ten largest fund houses' monthly portfolio file becomes one `fund_holdings`
row per fund (latest month wins). Public data only. A house whose files cannot be fetched is recorded in the run's
progress lines and left out; the run fails only when too few funds came through. Which of these stocks anyone holds
is matched in the browser, never here."""
import json
from collections.abc import Callable
from datetime import date
from pathlib import Path

from stockpilot.sources import fund_holdings as fh
from stockpilot.sources import fund_universe

KIND = "fundholdings"
DATASET = "fund_holdings"
LIMIT = 900                 # contract FUND_HOLDINGS_MAX
SOURCES = Path(__file__).resolve().parents[4] / "config" / "fund_house_sources.json"


def rows_from(houses: dict[str, dict]) -> list[dict]:
    """One row per fund: the house file with the latest 'as on' date wins."""
    best: dict[str, dict] = {}
    for got in houses.values():
        for m in got["matched"]:
            old = best.get(m["fund_id"])
            if old is None or (m["as_of"] or date.min) >= (old["as_of"] or date.min):
                best[m["fund_id"]] = m
    rows = []
    for fid, m in sorted(best.items()):
        holdings = [[r["isin"], r["name"], r["pct_nav"]] for r in m["rows"]]
        if holdings:
            rows.append({"id": fid, "name": m["name"], "amc": m["amc"],
                         "as_of": m["as_of"].isoformat() if m["as_of"] else None,
                         "holdings_json": json.dumps(holdings, separators=(",", ":"), ensure_ascii=False)})
    return rows[:LIMIT]


def collect(fetch: Callable[[str], bytes | None], sources: dict,
            progress: Callable[[str], None] = lambda _: None) -> list[dict]:
    blob = fetch(fund_universe.NAVALL_URL)
    if not blob:
        raise RuntimeError("AMFI's scheme list did not answer")
    funds = fund_universe.group_funds(fund_universe.parse_navall(blob))
    houses = {}
    for h in fh.HOUSES:
        try:
            urls, notes = fh.resolve_urls(fetch, sources.get(h))
            houses[h] = fh.load_house(fetch, urls, funds)
            houses[h]["failed"] += notes
        except Exception as err:  # noqa: BLE001 - one house failing leaves only that house out
            houses[h] = {"matched": [], "unmatched": [], "failed": [repr(err)]}
        g = houses[h]
        progress(f"{h}: {len(g['matched'])} funds, {len(g['failed'])} files unreadable"
                 if g["matched"] else f"{h}: cannot be fetched ({len(g['failed'])} problems)")
    return rows_from(houses)


def run(ctx, fetch: Callable[[str], bytes | None] | None = None) -> str:
    if fetch is None:
        from stockpilot.sources.http import fetch as http_fetch

        def fetch(u):  # noqa: E306
            return http_fetch(u, attempts=3, timeout=120)
    sources = json.loads(SOURCES.read_text())
    rows = collect(fetch, sources, progress=ctx.progress.line)
    ctx.publish(DATASET, rows, source="fund houses", as_of=str(ctx.range.end))
    return f"published holdings of {len(rows)} funds"
