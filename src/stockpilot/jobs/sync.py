"""The Sync job (ticket V2): the Kite callback creates it, the one-minute check runs it on the VM.

Steps are said as progress lines, so the page can show "logged in, fetching holdings, done, 3 changes". Kite is read through
the Worker's `GET /api/vm/kite` only (the token never leaves the Worker); no order endpoint exists in this module."""
from stockpilot.jobrun import JobFailed
from stockpilot.sources import kite

NEED_LOGIN = "No Kite login today. Press Sync again and log in."
NEED_LOGIN_BN = "আজ Kite-এ লগইন করা নেই। আবার Sync চাপুন আর লগইন করুন।"


def _positions(db) -> dict:
    """The latest saved snapshot as {(kind, isin or symbol): quantity}."""
    rows = db.execute("select kind, symbol, isin, quantity from holdings where snapshot_at = (select max(snapshot_at) from holdings)").fetchall()
    return {(k, i or s): q for k, s, i, q in rows}


def count_changes(before: dict, after: dict) -> int:
    """New, removed and resized holdings, each one change."""
    return sum(1 for key in before.keys() | after.keys() if abs(before.get(key, 0) - after.get(key, 0)) > 1e-9)


def _result(n: int) -> tuple[str, str]:
    if n == 0:
        return "Done, no changes", "হয়ে গেছে, কোনো বদল নেই"
    return (f"Done, {n} change{'s' if n != 1 else ''}", f"হয়ে গেছে, {n}টি বদল")


def handler(open_db, worker, close=lambda db: None):
    """A job handler for kind `sync`. `open_db()` gives the store, `worker` is a `kite.Worker`."""
    def run(ctx):
        ctx.progress("Checking Kite login", "Kite লগইন দেখা হচ্ছে")
        try:
            payload = kite.fetch(worker)
        except kite.LoginNeeded as err:
            raise JobFailed(NEED_LOGIN, NEED_LOGIN_BN) from err
        ctx.progress("Logged in, holdings fetched", "লগইন হয়েছে, হোল্ডিং এসেছে")
        ctx.progress("Saving holdings", "হোল্ডিং সেভ হচ্ছে")
        db = open_db()
        try:
            before = _positions(db)
            kite.store_payload(db, payload)
            changes = count_changes(before, _positions(db))
        finally:
            close(db)
        return _result(changes)[0]      # the runner writes the final ok line with these words
    return run
