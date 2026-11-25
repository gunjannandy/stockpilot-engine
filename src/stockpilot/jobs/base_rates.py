"""The monthly refresh of the base rates (first Sunday, 03:00): the whole price history through `backtest.monthly`, about 13
minutes under the 300 MB cap. It holds the database for that time, so the tick runs nothing else meanwhile. A failure is on
the Health tab through the run row and its problem."""
from stockpilot.analysis import backtest


def run(m, now, force: bool = False) -> dict:
    with m.db("base_rates") as db:
        try:
            notes = backtest.monthly(db, now.date())
        except Exception as err:  # noqa: BLE001 - journal.run has logged it; the tick carries on
            return {"status": "failed", "error": str(err)}
    return {"status": "skipped" if notes.get("note") else "ok", **notes}
