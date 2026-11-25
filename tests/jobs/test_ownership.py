"""Lane D: promoter holding and pledge from NSE's shareholding master and shareholding XBRL.
Fixtures are invented in the documented shape (the cloud cannot reach NSE); see docs/status/D3.md."""
import json
from datetime import date, datetime
from pathlib import Path

import pytest

from fakes import make_machine, settle
from stockpilot import backup, store
from stockpilot.jobs import due, ownership, tick

FIX = Path(__file__).parents[1] / "fixtures" / "ownership"
MASTER = json.loads((FIX / "master_ABCCO.json").read_text())


def xbrl(name):
    return (FIX / name).read_bytes()


def fetchers(master=None, calls=None, files=None):
    calls = calls if calls is not None else []

    def fetch_json(path):
        calls.append(path)
        return master if master is not None else MASTER

    def fetch_file(url, max_bytes=0):
        calls.append(url)
        name = url.rsplit("/", 1)[-1]
        if files is not None and name not in files:
            raise OSError("down")
        return xbrl(name)
    return fetch_json, fetch_file, calls


# ---- parsing -------------------------------------------------------------------------------

def test_master_gives_one_filing_per_quarter_and_the_revised_one_wins():
    filings = ownership.parse_master(MASTER)
    by_q = {f.quarter_end: f for f in filings}
    assert len(filings) == 6 and sorted(by_q, reverse=True)[0] == date(2026, 9, 30)
    jun = by_q[date(2026, 6, 30)]
    assert jun.xbrl_url.endswith("SHP_ABCCO_062026_rev.xml") and jun.filed_on == date(2026, 8, 20)
    assert (by_q[date(2026, 9, 30)].promoter_pct, by_q[date(2026, 9, 30)].public_pct) == (62.5, 37.5)
    assert by_q[date(2025, 6, 30)].xbrl_url is None


def test_master_accepts_a_data_wrapper_and_skips_rows_without_numbers():
    assert len(ownership.parse_master({"data": MASTER[:1]})) == 1
    assert ownership.parse_master([{"symbol": "X", "date": "30-SEP-2026", "pr_and_prgrp": "-"}, {}]) == []
    assert ownership.parse_master(None) == []


def test_xbrl_reads_the_promoter_group_total_and_its_pledge():
    assert ownership.parse_xbrl(xbrl("SHP_ABCCO_092026.xml")) == {"promoter_pct": 62.5, "pledge_pct": 12.4}


def test_a_filing_with_no_pledge_element_is_unknown_not_zero():
    assert ownership.parse_xbrl(xbrl("SHP_ABCCO_032026.xml")) == {"promoter_pct": 61.0, "pledge_pct": None}


def test_a_filing_with_no_promoter_context_or_not_xml_gives_nothing():
    assert ownership.parse_xbrl(xbrl("SHP_nomember.xml")) == {"promoter_pct": None, "pledge_pct": None}
    assert ownership.parse_xbrl(b"<html>blocked</html") == {"promoter_pct": None, "pledge_pct": None}


# ---- storing -------------------------------------------------------------------------------

def rows(db):
    return db.execute("select quarter_end, promoter_pct, pledge_pct, pledge_checked from ownership where symbol = 'ABCCO' "
                      "order by quarter_end desc").fetchall()


def test_ingest_stores_the_newest_five_quarters_with_pledge(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    fj, ff, calls = fetchers()
    out = ownership.ingest(db, ["ABCCO"], fj, ff)
    assert out == {"symbols": 1, "quarters": 5, "pledge_read": 5, "failed": 0}
    assert rows(db) == [(date(2026, 9, 30), 62.5, 12.4, True), (date(2026, 6, 30), 62.1, 14.0, True),
                        (date(2026, 3, 31), 61.0, None, True), (date(2025, 12, 31), 61.0, 0.0, True),
                        (date(2025, 9, 30), 60.0, 0.0, True)]
    assert calls[0] == "/api/corporate-share-holdings-master?index=equities&symbol=ABCCO"


def test_a_second_run_stores_nothing_new_and_fetches_no_xbrl(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    ownership.ingest(db, ["ABCCO"], *fetchers()[:2])
    before = rows(db)
    fj, ff, calls = fetchers()
    out = ownership.ingest(db, ["ABCCO"], fj, ff)
    assert rows(db) == before and out["pledge_read"] == 0
    assert calls == ["/api/corporate-share-holdings-master?index=equities&symbol=ABCCO"]


def test_a_new_quarter_adds_one_row_and_reads_only_its_xbrl(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    old = [r for r in MASTER if "SEP-2026" not in r["date"]]
    ownership.ingest(db, ["ABCCO"], *fetchers(master=old)[:2])
    assert len(rows(db)) == 5 and rows(db)[0][0] == date(2026, 6, 30)
    fj, ff, calls = fetchers()
    ownership.ingest(db, ["ABCCO"], fj, ff)
    assert rows(db)[0] == (date(2026, 9, 30), 62.5, 12.4, True)
    assert [c for c in calls if c.endswith(".xml")] == ["https://example.test/xbrl/SHP_ABCCO_092026.xml"]


def test_a_revised_filing_replaces_the_stored_quarter(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    first = [r for r in MASTER if "rev" not in r["xbrl"]]
    ownership.ingest(db, ["ABCCO"], *fetchers(master=first)[:2])
    assert db.execute("select pledge_pct from ownership where quarter_end = '2026-06-30'").fetchone() == (99.0,)
    ownership.ingest(db, ["ABCCO"], *fetchers()[:2])
    assert db.execute("select pledge_pct from ownership where quarter_end = '2026-06-30'").fetchone() == (14.0,)


def test_a_failed_xbrl_keeps_the_promoter_number_and_is_retried_next_run(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    fj, ff, _ = fetchers(files={"SHP_ABCCO_062026_rev.xml", "SHP_ABCCO_032026.xml", "SHP_ABCCO_122025.xml", "SHP_ABCCO_092025.xml"})
    out = ownership.ingest(db, ["ABCCO"], fj, ff)
    assert out["failed"] == 1 and out["quarters"] == 5
    assert rows(db)[0] == (date(2026, 9, 30), 62.5, None, False)
    ownership.ingest(db, ["ABCCO"], *fetchers()[:2])
    assert rows(db)[0] == (date(2026, 9, 30), 62.5, 12.4, True)


def test_one_stock_failing_does_not_stop_the_rest_but_all_failing_raises(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")

    def fj(path):
        if "symbol=BAD" in path:
            raise OSError("blocked")
        return MASTER
    out = ownership.ingest(db, ["BAD", "ABCCO"], fj, fetchers()[1])
    assert out["failed"] == 1 and out["quarters"] == 5
    with pytest.raises(RuntimeError):
        ownership.ingest(db, ["BAD"], fj, fetchers()[1])


def test_a_master_with_a_different_symbol_row_is_ignored(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    other = [{**MASTER[0], "symbol": "OTHER"}]
    assert ownership.ingest(db, ["ABCCO"], *fetchers(master=other)[:2])["quarters"] == 0


def test_the_table_is_in_a_backup_list():
    assert "ownership" in backup.MARKET_TABLES


# ---- which stocks, and the job -------------------------------------------------------------

def test_panes_are_the_held_watched_and_called_stocks(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    db.execute("insert into holdings values ('2026-11-20 09:00', 'stock', 'HELDCO', 'INE000000001', 5, 100, 'kite')")
    db.execute("insert into holdings values ('2026-11-20 09:00', 'mf', 'SOMEFUND', 'INF000000001', 5, 100, 'kite')")
    db.execute("insert into watchlist (symbol, exchange, added_by) values ('WATCHCO', 'NSE', 'x')")
    db.execute("insert into watchlist (symbol, exchange, added_by, removed_at) values ('GONECO', 'NSE', 'x', now())")
    assert ownership.pane_symbols(db) == ["HELDCO", "WATCHCO"]


def test_the_job_runs_and_records_a_run_row(tmp_path):
    m = make_machine(tmp_path, now=datetime(2026, 11, 20, 10, 3), fetch_json=fetchers()[0], fetch_file=fetchers()[1])
    with m.db("seed") as db:
        db.execute("insert into watchlist (symbol, exchange, added_by) values ('ABCCO', 'NSE', 'x')")
    out = ownership.run(m, m.clock())
    assert out["status"] == "ok" and out["quarters"] == 5
    with m.db("check") as db:
        assert db.execute("select status from runs where job = 'ownership'").fetchone() == ("ok",)


def test_the_job_fails_loudly_when_nse_blocks_every_stock(tmp_path):
    def blocked(path):
        raise OSError("403")
    m = make_machine(tmp_path, now=datetime(2026, 11, 20, 10, 3), fetch_json=blocked)
    with m.db("seed") as db:
        db.execute("insert into watchlist (symbol, exchange, added_by) values ('ABCCO', 'NSE', 'x')")
    assert ownership.run(m, m.clock())["status"] == "failed"


# ---- when it is due: weekday working hours only (systemd units 09:00 to 17:00 IST) ------------

FRIDAY = datetime(2026, 11, 20)


@pytest.mark.parametrize("state, hour, expect", [
    (due.State(), 8, ["queue"]),
    (due.State(), 9, ["queue", "ownership"]),
    (due.State(), 16, ["queue", "gather"]),                        # gather has the 16:00 slot
    (due.State(ownership_done=True), 12, ["queue"]),
    (due.State(ownership_runs=2), 12, ["queue"]),
    (due.State(trading_day=False), 12, ["queue"]),
    (due.State(ownership_done=True, rerun=frozenset({"ownership"})), 12, ["queue", "ownership"]),
])
def test_when_ownership_is_due(state, hour, expect):
    assert due.due(state, FRIDAY.replace(hour=hour, minute=3)) == expect


def test_read_state_counts_todays_ownership_runs(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    db.execute("insert into runs (job, started_at, status) values ('ownership', '2026-11-20 10:05', 'failed')")
    state = due.read_state(db, datetime(2026, 11, 20, 10, 30), tmp_path)
    assert (state.ownership_done, state.ownership_runs) == (False, 1)
    db.execute("insert into runs (job, started_at, status) values ('ownership', '2026-11-20 10:15', 'ok')")
    assert due.read_state(db, datetime(2026, 11, 20, 10, 30), tmp_path).ownership_done


def test_the_tick_runs_ownership_in_the_morning(tmp_path):
    m = make_machine(tmp_path, now=datetime(2026, 11, 20, 10, 3), fetch_json=fetchers()[0], fetch_file=fetchers()[1])
    with m.db("seed") as db:
        db.execute("insert into watchlist (symbol, exchange, added_by) values ('ABCCO', 'NSE', 'x')")
    report = tick.run(m)
    assert report["ownership"]["status"] == "ok"


def test_sp_ownership_is_a_command(monkeypatch, capsys):
    from stockpilot import cli
    monkeypatch.setattr(cli, "cmd_ownership", lambda args, cfg: 0)      # only the wiring: the job itself is tested above
    import sys
    parsed = []
    monkeypatch.setattr(sys, "argv", ["sp", "ownership", "--help"])
    with pytest.raises(SystemExit) as e:
        cli.main(["ownership", "--help"])
    assert e.value.code == 0 and "usage: sp ownership" in capsys.readouterr().out


# Real NSE files (trimmed, public data; docs/status/R-run.md): the values are fractions, the pledge element has another
# name, and a company that pledges nothing carries only a "false" flag.
def test_real_filing_with_a_pledge_reads_percent_of_promoters_own_shares():
    assert ownership.parse_xbrl(xbrl("SHP_real_pledged.xml")) == {"promoter_pct": 1.95, "pledge_pct": 4.65}


def test_real_filing_that_says_nothing_is_pledged_gives_zero_pledge():
    assert ownership.parse_xbrl(xbrl("SHP_real_nopledge.xml")) == {"promoter_pct": 50.98, "pledge_pct": 0.0}


def test_the_master_percent_is_kept_when_the_xbrl_is_read(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    fj, _, _ = fetchers()
    ownership.ingest(db, ["ABCCO"], fj, lambda url, max_bytes=0: xbrl("SHP_real_nopledge.xml"), keep=1)
    assert db.execute("select promoter_pct, pledge_pct from ownership").fetchone() == (62.5, 0.0)
