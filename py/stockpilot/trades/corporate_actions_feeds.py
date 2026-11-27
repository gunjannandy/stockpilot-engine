"""Corporate actions NSE keeps outside its main-board feed. `index=equities` lists main-board stocks only; ETF and
fund units sit under `index=mf` and SME stocks under `index=sme`. Same row shape, so `corporate_actions.from_nse`
reads them: a unit split or an SME bonus is a split or bonus like any other, and the lots rebuild and the
price adjustment pick it up."""
from datetime import date, timedelta

from stockpilot.trades import corporate_actions as ca

FEEDS = ("mf", "sme")
LOG = "nse_corporate_actions_{}"


def window_path(feed: str, first: date, last: date) -> str:
    return ca.window_path(first, last).replace("index=equities", f"index={feed}")


def _known(db, a) -> bool:
    return bool(db.execute("select 1 from corporate_actions where symbol = ? and ex_date = ? and kind = ?",
                           [a.symbol, a.ex_date, a.kind]).fetchone())


def _fetch(feed, fetch_json, first, last, failed):
    try:
        return [a for a in (ca.from_nse(r) for r in fetch_json(window_path(feed, first, last)) or []) if a]
    except Exception as err:  # noqa: BLE001 - the other feed is still read; the failure is raised at the end
        failed[feed] = repr(err)
        return None


def _finish(failed):
    if failed:
        raise RuntimeError("NSE corporate-action feed failed: " + "; ".join(f"{k}: {v}" for k, v in failed.items()))


def ingest(db, day: date, fetch_json) -> int:
    """Daily, like `corporate_actions.ingest`: a week back and six weeks ahead, every feed. Returns actions stored."""
    found, new, failed = [], False, {}
    for feed in FEEDS:
        acts = _fetch(feed, fetch_json, day - timedelta(days=ca.LOOK_BACK_DAYS),
                      day + timedelta(days=ca.LOOK_AHEAD_DAYS), failed)
        if acts is not None:
            new |= any(not _known(db, a) for a in acts)
            found += acts
    ca.save(db, found)
    ca._restate_lots(db, new)
    _finish(failed)
    return len(found)


def backfill(db, fetch_json, since: date, today: date) -> int:
    """History, one month per request per feed; a finished month is logged and never fetched again."""
    found, new, failed = 0, False, {}
    for feed in FEEDS:
        for first, last in ca._months(since, today):
            period = first.strftime("%Y-%m")
            if db.execute("select 1 from fetch_log where source = ? and period = ?", [LOG.format(feed), period]).fetchone():
                continue
            acts = _fetch(feed, fetch_json, first, last, failed)
            if acts is None:
                break                       # blocked: the next run resumes at this month
            new |= any(not _known(db, a) for a in acts)
            found += ca.save(db, acts)
            if last < today:
                db.execute("insert into fetch_log values (?, ?)", [LOG.format(feed), period])
    ca._restate_lots(db, new)
    _finish(failed)
    return found
