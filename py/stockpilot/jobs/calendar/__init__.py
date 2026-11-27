"""The calendar Job (decisions §2 Schedules): public data only, run from GitHub Actions because
Cloudflare's addresses are often refused by NSE and BSE.

Fetches the trading holidays and the corporate actions (splits, bonuses, symbol changes, delistings) around
today, and publishes them as the `calendar` dataset. The Worker's calendar module reads the current run;
health turns amber when it covers fewer than 30 days ahead.
"""
import re
from collections.abc import Callable
from datetime import date, datetime, timedelta
from fractions import Fraction

from stockpilot.runtime import JobContext, row_id
from stockpilot.trades import corporate_actions as ca
from stockpilot.trades import corporate_actions_feeds as feeds

KIND = "calendar"
DATASET = "calendar"
HOLIDAYS_PATH = "/api/holiday-master?type=trading"
LOOK_BACK_DAYS, LOOK_AHEAD_DAYS = ca.LOOK_BACK_DAYS, 365   # a year of holidays keeps health green; actions are known ~6 weeks out
ACTION_AHEAD_DAYS = ca.LOOK_AHEAD_DAYS

_CHANGE = re.compile(r"(?:symbol|name)\b.*?\bfrom\s+([A-Z0-9&-]+)\s+to\s+([A-Z0-9&-]+)", re.I)
_BLANK = {"reason": None, "symbol": None, "old_shares": None, "new_shares": None, "new_symbol": None}


def _row(kind: str, day: date, **fields) -> dict:
    key = [kind, str(day), fields.get("symbol"), fields.get("new_symbol")]
    return {**_BLANK, "id": f"{kind}-{day}-{row_id(*key)[:8]}", "kind": kind, "date": str(day), **fields}


def holiday_rows(payload: dict) -> list[dict]:
    """NSE's trading-holiday list (the equity segment, `CM`) as `holiday` rows."""
    return [_row("holiday", datetime.strptime(h["tradingDate"], "%d-%b-%Y").date(), reason=h["description"].strip())
            for h in payload.get("CM", [])]


def action_rows(raw: list[dict]) -> list[dict]:
    """NSE corporate-action rows as `split`, `bonus`, `symbol_change` and `delisting` rows.

    Demergers and rights issues have no share ratio and are not calendar facts, so they are left out."""
    rows = []
    for r in raw:
        subject = r.get("subject", "") or ""
        sym = r.get("symbol") or ""
        a = ca.from_nse(r)
        if a and a.kind in ("split", "bonus"):
            ratio = Fraction(a.numerator / a.denominator).limit_denominator(1000)
            if ratio > 0:
                rows.append(_row(a.kind, a.ex_date, symbol=a.symbol, old_shares=ratio.denominator, new_shares=ratio.numerator))
            continue
        ex = ca._day(r.get("exDate"))
        if not ex or not sym:
            continue
        if "delist" in subject.lower():
            rows.append(_row("delisting", ex, symbol=sym))
        elif (m := _CHANGE.search(subject)) and m[1].upper() != m[2].upper():
            rows.append(_row("symbol_change", ex, symbol=m[1].upper(), new_symbol=m[2].upper()))
    return rows


def collect(day: date, fetch_json: Callable[[str], object]) -> list[dict]:
    """Every row for `day`. The holiday list failing fails the Job; one corporate-action feed failing does not hide the others."""
    rows = holiday_rows(fetch_json(HOLIDAYS_PATH))  # type: ignore[arg-type]
    failed = {}
    for feed in ("equities", *feeds.FEEDS):
        first, last = day - timedelta(days=LOOK_BACK_DAYS), day + timedelta(days=ACTION_AHEAD_DAYS)
        path = ca.window_path(first, last) if feed == "equities" else feeds.window_path(feed, first, last)
        try:
            rows += action_rows(fetch_json(path) or [])  # type: ignore[arg-type]
        except Exception as err:  # noqa: BLE001 - the other feeds are still read
            failed[feed] = repr(err)
    if failed and len(failed) == len(("equities", *feeds.FEEDS)):
        raise RuntimeError("every NSE corporate-action feed failed: " + "; ".join(f"{k}: {v}" for k, v in failed.items()))
    return rows


def run(ctx: JobContext, fetch_json: Callable[[str], object] | None = None) -> str:
    if fetch_json is None:
        from stockpilot.sources.nse_api import Session

        fetch_json = Session().fetch_json
    day = ctx.range.end
    rows = collect(day, fetch_json)
    ctx.progress.line(f"read {sum(r['kind'] == 'holiday' for r in rows)} holidays and {sum(r['kind'] != 'holiday' for r in rows)} corporate actions")
    ctx.publish(DATASET, rows, source="nse", as_of=str(day))
    return f"published {len(rows)} calendar rows"
