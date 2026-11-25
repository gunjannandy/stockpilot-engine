"""The dashboard's requests: poll the Worker, apply each, acknowledge it. Runs first on every tick."""
from stockpilot import journal, vmqueue
from stockpilot.jobs import docs, due, ship


def context(m) -> vmqueue.Context:
    """What the heavier handlers need. Each one lets go of the database while the bridge or wrangler works."""
    def sync(db):
        bridge, pan = m.bridge()
        return docs.sync_docs(db, bridge, pan)

    return vmqueue.Context(sync_docs=sync, build_pack=lambda db: ship.build_tax_pack(db, m.cfg),
                           publish=lambda db: ship.publish(m, db), gh=m.gh, git=m.git,
                           rerun=lambda job: due.ask_rerun(m.root, job))


def run(m, now=None, force: bool = False) -> dict:
    with m.db("queue") as db:
        if m.worker is None:
            m.cfg.require("SP_VM_KEY")           # says what is missing
        ctx = context(m)
        counts = journal.tracked(db, "queue", lambda: vmqueue.poll(db, m.worker, ctx))
        if counts and (counts.get("done") or counts.get("failed")):
            ship.protect_state(m, db, "queue")        # a request changed owner state
        stamp = (now or m.clock()).replace(microsecond=0)    # the machine's clock, not the database's: runs are dated by it
        db.execute("delete from runs where job = 'queue' and status = 'ok' and started_at < ? - interval 3 day", [stamp])
    return counts
