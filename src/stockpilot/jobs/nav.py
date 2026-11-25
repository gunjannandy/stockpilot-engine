"""AMFI fund NAVs after 23:30, then the page is rebuilt so the funds show tonight's values."""
from stockpilot import journal
from stockpilot.sources import funds
from stockpilot.jobs import ship


def run(m, now, force: bool = False) -> dict:
    with m.db("nav") as db:
        counts = journal.tracked(db, "nav", lambda: {"navs": funds.ingest_navall(db, db.releasing(m.fetch))})
        try:
            note = ship.publish(m, db, today=now.date())
        except RuntimeError as err:          # on the Health tab already; the next day's run deploys again
            return {"status": "failed", **counts, "error": str(err)}
    return {"status": "ok", **counts, "note": note}
