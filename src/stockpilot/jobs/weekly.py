"""The Saturday review. Refreshes run in steps that each record they are done; the slow ones (filings, Yahoo
fundamentals, documents) work in batches of 200 and each batch ends the tick, so the queue runs between them and the
next tick goes on. When every step is done the analysis runs, then the vault and the market backup.

Progress lives in `fetch_log` as `weekly:<saturday>:<step>`, so a stop at any point resumes where it was."""
from datetime import date, datetime, timedelta

from stockpilot import backup, fundcall, journal, store

from stockpilot.sources import fundamentals, fundcosts, funds, fx, usprices

from stockpilot.analysis import screen
from stockpilot import weekly as analysis
from stockpilot.jobs import docs, ship
from stockpilot.sources import filings

BATCH = 200
YAHOO_PAUSE_S = 0.5


def saturday_of(day: date) -> date:
    return day - timedelta(days=(day.weekday() - 5) % 7)


def _progress(db, key: str):
    row = db.execute("select period from fetch_log where source = ?", [key]).fetchone()
    return row[0] if row else None


def _set(db, key: str, value: str) -> None:
    db.execute("delete from fetch_log where source = ?", [key])
    db.execute("insert into fetch_log values (?, ?)", [key, value])


def _nav(m, db, now, floor):
    last = db.execute("select max(started_at) from runs where job = 'nav' and status in ('ok', 'partial')").fetchone()[0]
    if last and now - last < timedelta(hours=24):
        return False, "NAVs fetched in the last 24 hours"
    return False, f"{funds.ingest_navall(db, db.releasing(m.fetch))} NAVs"


def _fund_costs(m, db, now, floor):
    cfg = m.cfg
    if cfg.get("funds.ter_url") or cfg.get("funds.aum_url"):    # owner-supplied files win when configured
        return False, f"{fundcosts.refresh(db, now.date(), cfg.get('funds.ter_url'), cfg.get('funds.aum_url'), db.releasing(m.fetch))} costs"
    note = f"{fundcosts.refresh_api(db, now.date(), db.releasing(m.fetch))} costs (AMFI)"
    try:                                                        # fund size; a failure leaves the costs standing (lane M)
        note += f", {fundcosts.refresh_aum_api(db, now.date(), db.releasing(m.fetch))} sizes"
    except Exception as err:  # noqa: BLE001
        journal.problem(db, "weekly", f"fund sizes: {err!r}")
        note += f", sizes failed: {err!r}"
    return False, note


def _us_prices(m, db, now, floor):
    return False, f"{usprices.refresh(db, db.releasing(m.yahoo_history), now.date())} US prices"


def _usdinr(m, db, now, floor):
    year = usprices.first_year(db)
    return False, (f"{fx.ingest_usdinr_range(db, date(year, 1, 1), now.date(), db.releasing(m.fetch))} rates" if year else "no US lots")


def _slice(db, key: str, items: list) -> tuple[list, int, bool]:
    """The next BATCH of `items` after the saved offset: (batch, offset after it, more left)."""
    start = int(_progress(db, key) or 0)
    batch = items[start:start + BATCH]
    return batch, start + len(batch), start + len(batch) < len(items)


def _filings(m, db, now, floor, key):
    batch, end, more = _slice(db, key, filings.symbols_to_load(db, now.date(), floor))
    totals = filings.refresh(db, db.releasing(m.fetch_json), db.releasing(m.fetch_file), batch, now.date())
    _set(db, key, str(end))
    return more, f"filings {end}: {totals['stored']} quarters stored for {totals['companies']} companies"


def _fundamentals(m, db, now, floor, key):
    batch, end, more = _slice(db, key, fundamentals.pool(db, now.date(), floor))
    db.suspend()                                    # Yahoo is slow: fetch the whole batch with the lock free
    data = {}
    for symbol in batch:
        try:
            data[symbol] = m.yahoo(symbol)
        except Exception:  # noqa: BLE001 - one bad ticker must not stop the batch (refresh counts it missing)
            data[symbol] = None
        m.sleep(YAHOO_PAUSE_S)
    result = fundamentals.refresh(db, batch, now.date(), data.get)
    _set(db, key, str(end))
    return more, f"fundamentals {end}: {result['stored']} stored, {len(result['missing'])} missing"


def _documents(m, db, now, floor, key):
    note, more = docs.sync_safely(m, db, "weekly", limit=BATCH)
    return more, note


STEPS = [("nav", _nav, False), ("fund costs", _fund_costs, False), ("US prices", _us_prices, False),
         ("USD/INR", _usdinr, False), ("filings", _filings, True), ("fundamentals", _fundamentals, True),
         ("documents", _documents, True)]


def run(m, now: datetime, force: bool = False, analyse_only: bool = False) -> dict:
    cfg, day = m.cfg, now.date()
    floor = cfg.get("universe.liquidity_floor_cr", 1.0)
    week = f"weekly:{saturday_of(day)}"
    notes = []
    with m.db("weekly") as db:
        if force:
            db.execute("delete from fetch_log where source like ?", [week + ":%"])
        for name, step, batched in ([] if analyse_only else STEPS):
            key = f"{week}:{name}"
            if _progress(db, key) == "done":
                continue
            try:
                more, note = step(m, db, now, floor, key) if batched else step(m, db, now, floor)
            except store.Busy:
                raise
            except Exception as err:  # noqa: BLE001 - a failed refresh must not stop the analysis of what is stored
                journal.problem(db, "weekly", f"{name} refresh: {err!r}")
                more, note = False, f"{name} failed: {err!r}"
            notes.append(note)
            if more:
                return {"status": "more", "notes": notes}         # the next tick goes on
            _set(db, key, "done")
        screen.run(db, day, floor, fresh=True)                       # new fundamentals: one fresh screen for the analysis
        private = analysis.load_private(cfg.root)
        result = analysis.run(db, day, cfg.root / cfg.get("tax.pack_dir", "data/tax_pack"), target=private["target"],
                              liquidity_floor_cr=floor, private=private)
        if m.analyse:                                                # R13: the fund calls; a failure leaves the plain review standing
            try:
                fc = fundcall.run(db, day, db.releasing(m.analyse), m.runners, cfg.get("funds.exit_loads"))
                notes.append(f"fund calls: {fc['funds']} funds, {fc['calls']}")
            except store.Busy:
                raise
            except Exception as err:  # noqa: BLE001
                journal.problem(db, "weekly", f"fund calls: {err!r}")
                notes.append(f"fund calls failed: {err!r}")
        if analyse_only:
            return {**result, "notes": notes}
        notes.append(f"vault: {ship.protect_state(m, db, 'weekly')}")
        if (cfg.root / "config" / "vault.pub").exists() and m.upload_market:
            try:
                from stockpilot import vault
                keys = vault.Keys.load(cfg.root / "config")
                notes.append(f"market backup: {backup.backup_market(db, keys.recipient, db.releasing(m.upload_market))}")
            except Exception as err:  # noqa: BLE001
                journal.problem(db, "weekly", f"market backup: {err!r}")
    return {**result, "notes": notes}
