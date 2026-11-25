"""The DuckDB store. open() takes the one writer lock, then applies any pending migrations, so callers always see
the current schema and never meet a second writer."""
import fcntl
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

# Append only: never edit a migration once it has shipped; add a new one.
MIGRATIONS = [
    """
    create table prices (
        date date, symbol varchar, exchange varchar, series varchar,
        open double, high double, low double, close double, prev_close double,
        volume bigint, value double, trades bigint,
        primary key (date, symbol, exchange));
    create table fundamentals (
        as_of date, symbol varchar, metric varchar, value double, source varchar,
        primary key (as_of, symbol, metric));
    create table holdings (
        snapshot_at timestamp, kind varchar, symbol varchar, isin varchar,
        quantity double, avg_price double, source varchar);
    create sequence lot_id;
    create table lots (
        id bigint default nextval('lot_id') primary key, kind varchar, symbol varchar, isin varchar,
        acquired_on date, quantity double, cost_per_unit double, currency varchar default 'INR',
        closed_quantity double default 0, source varchar, source_ref varchar);
    create table watchlist (
        symbol varchar, exchange varchar, added_by varchar,
        added_at timestamp default current_timestamp, removed_at timestamp);
    create sequence run_id;
    create table runs (
        id bigint default nextval('run_id') primary key, job varchar,
        started_at timestamp default current_timestamp, finished_at timestamp,
        status varchar, notes json);
    create sequence call_id;
    create table calls (
        id bigint default nextval('call_id') primary key, run_id bigint, made_on date,
        symbol varchar, kind varchar, action varchar, probability double, base_rate double,
        horizon_days integer, entry double, stop double, target double, size_inr double,
        reasons json, risks json, news json, runner varchar, skeptic varchar, unproven boolean,
        score_1m double, score_3m double, score_6m double);
    create sequence request_id;
    create table requests (
        id bigint default nextval('request_id') primary key, kind varchar, payload json,
        created_at timestamp default current_timestamp, applied_at timestamp, status varchar);
    create sequence problem_id;
    create table problems (
        id bigint default nextval('problem_id') primary key, seen_at timestamp default current_timestamp,
        job varchar, severity varchar, message varchar, resolution varchar, issue_url varchar);
    """,
    """
    create table holidays (date date primary key, description varchar);
    create table surveillance (as_of date, symbol varchar, label varchar, primary key (as_of, symbol));
    """,
    """
    create table funds (scheme_code integer primary key, isin_growth varchar, isin_reinvest varchar,
        name varchar, plan varchar, option varchar, category varchar, house varchar);
    create table navs (date date, scheme_code integer, nav double, primary key (date, scheme_code));
    create table fx (date date, pair varchar, rate double, primary key (date, pair));
    """,
    """
    create table announcements (announced_at timestamp, symbol varchar, subject varchar, text varchar,
        url varchar, primary key (announced_at, symbol, subject));
    """,
    """
    create table index_levels (date date, name varchar, close double, pe double, pb double, dy double,
        primary key (date, name));
    """,
    """
    create table stocks (symbol varchar primary key, name varchar, industry varchar, isin varchar);
    """,
    """
    create table base_rates (factor varchar, bucket integer, regime varchar, horizon_days integer,
        n integer, hit_rate double, avg_excess double, computed_on date,
        primary key (factor, bucket, regime, horizon_days));
    """,
    """
    create table budgets (month varchar primary key, amount_inr double, set_by varchar,
        set_at timestamp default current_timestamp);
    create sequence allocation_id;
    create table target_allocations (id bigint default nextval('allocation_id') primary key,
        allocation json, approved_by varchar, approved_at timestamp default current_timestamp);
    create table kite_syncs (fetched_at timestamp primary key, trades json, positions json,
        margins json, gtts json);
    alter table requests add column remote_id varchar;
    alter table requests add column requested_by varchar;
    alter table requests add column note varchar;
    alter table requests add column acked boolean default false;
    """,
    """
    create table site_extras (name varchar primary key, built_on date, body json);
    """,
    """
    create sequence trade_id;
    create table trades (
        id bigint default nextval('trade_id') primary key, trade_key varchar unique, source varchar,
        source_ref varchar, kind varchar, symbol varchar, isin varchar, side varchar, trade_date date,
        quantity double, price double, currency varchar default 'INR', status varchar default 'confirmed');
    create table corporate_actions (
        symbol varchar, isin varchar, ex_date date, kind varchar, numerator double, denominator double,
        subject varchar, primary key (symbol, ex_date, kind));
    """,
    """
    create sequence sale_id;
    create table sales (
        id bigint default nextval('sale_id') primary key, kind varchar, symbol varchar, isin varchar,
        sold_on date, quantity double, price_per_unit double, currency varchar default 'INR',
        expenses double default 0, source varchar, source_ref varchar);
    create table weekly_reports (week_of date, section varchar, payload json, primary key (week_of, section));
    """,
    """
    create table fetch_log (source varchar, period varchar, primary key (source, period));
    alter table corporate_actions add column source varchar default 'nse';
    """,
    """
    -- one row per Drive file or mail the feed has handled; `version` is the Drive modified time plus the parser
    -- version, so an unchanged document is never downloaded or parsed twice
    create table documents (id varchar primary key, source varchar, kind varchar, name varchar, version varchar,
        outcome varchar, reason varchar, trades integer, handled_at timestamp default current_timestamp);
    """,
    """
    -- quantity per ISIN on a CDSL statement date: the check on the lots built from trades
    create table holding_statements (as_of date, isin varchar, quantity double, primary key (as_of, isin));
    """,
    """
    create table fund_costs (key varchar, as_of date, ter_regular double, ter_direct double, aum_cr double,
        primary key (key, as_of));
    """,
    """
    -- journal: a repeated unresolved problem bumps count and last_seen instead of adding a row
    alter table problems add column key varchar;
    alter table problems add column count integer default 1;
    alter table problems add column last_seen timestamp;
    update problems set key = message, count = 1, last_seen = seen_at;
    """,
    """
    -- dossier sources (R3): each is one NSE public file or feed, stored as it was published
    create table delivery (date date, symbol varchar, series varchar, deliv_qty bigint, deliv_pct double,
        primary key (date, symbol, series));
    create table deals (date date, symbol varchar, kind varchar, client varchar, side varchar,
        quantity bigint, price double);
    create table results_calendar (symbol varchar, date date, purpose varchar, detail varchar,
        primary key (symbol, date, purpose));
    create table flows (date date, category varchar, buy_cr double, sell_cr double, net_cr double,
        primary key (date, category));
    create table filings_index (isin varchar, symbol varchar, period_from date, period_to date,
        consolidated boolean, audited boolean, filed_at timestamp, xbrl_url varchar,
        primary key (symbol, period_from, period_to, consolidated, audited, filed_at));
    create table headlines (symbol varchar, published_at timestamp, title varchar, source varchar,
        url varchar, fetched_on date, primary key (symbol, url));
    """,
    # R9: quarterly results parsed from the NSE XBRL filings, in rupees. filed_at is part of the key so a
    # restatement is a second row and `filings.history` can answer "what was known on that day".
    """
    create table quarterly (isin varchar, symbol varchar, period_end date, consolidated boolean,
        filed_at timestamp, revenue double, operating_profit double, net_profit double, eps double,
        source_url varchar, primary key (symbol, period_end, consolidated, filed_at));
    """,
    """
    -- R4 forecaster: the calls row keeps what the page shows; not_now is the owners' set-aside list (R5 writes it);
    -- archived_days freezes a day once the archive branch has it
    alter table calls add column section varchar;
    alter table calls add column expected_gain_inr double;
    alter table calls add column hurdle double;
    alter table calls add column change_reason varchar;
    alter table calls add column summary_bn varchar;
    alter table calls add column would_buy_if varchar;
    alter table calls add column level_flag varchar;
    alter table calls add column warnings json;
    alter table calls add column acted_on date;
    alter table calls add column base_rate_n integer;
    create sequence not_now_id;
    create table not_now (
        id bigint default nextval('not_now_id') primary key, symbol varchar, scope varchar, until date,
        set_by varchar, set_at timestamp default current_timestamp, undone_at timestamp);
    create table archived_days (day date primary key, archived_at timestamp default current_timestamp);
    """,
    # R8: who placed each trade (Dad in Kite, or a smallcase order). `trade_tags` is derived and rewritten on every
    # sync from `trades` and `smallcase_orders`; `trades` itself is never touched. A demerger is a corporate action
    # with a new ISIN and the share of cost that moves to it; a rights issue carries the price paid. Payslip and Form 16 perquisites feed the RSU check.
    """
    create table smallcase_orders (order_key varchar primary key, basket varchar, order_date date, name varchar,
        side varchar, quantity double, price double, source_ref varchar);
    create table trade_tags (trade_key varchar primary key, placed_by varchar, basket varchar, how varchar);
    create table payslip_perquisites (kind varchar, period varchar, perquisite_inr double, source_ref varchar,
        primary key (kind, period));
    create table action_terms (symbol varchar, ex_date date, kind varchar, new_isin varchar, new_symbol varchar,
        cost_fraction double, price double, primary key (symbol, ex_date, kind));
    """,
    """
    -- the screen, computed once per trading day; site.build, opportunities and the decide step read it
    create table screens (as_of date primary key, payload json);
    """,
    # R6: the base rate in 40 buckets (momentum x regime x volatility x liquidity) beside the older momentum x regime
    # table, which stays in step with it; `calls.raw_probability` is what the model said, `probability` what code decided on.
    """
    create table base_rate_buckets (horizon_days integer, momentum integer, regime varchar, vol varchar, liquidity varchar,
        n integer, hit_rate double, avg_excess double, computed_on date,
        primary key (horizon_days, momentum, regime, vol, liquidity));
    alter table calls add column raw_probability double;
    """,
    # R5b: how a stock was set aside. 'snooze' ends on its own (30 days); 'dismiss' lasts until undone.
    """
    alter table not_now add column how varchar;
    update not_now set how = case when until is null then 'dismiss' else 'snooze' end;
    """,
    # R12: the owners' feedback inbox. status: new -> auto | backlog -> applied | declined; backlog_id is the GitHub issue number.
    """
    create sequence feedback_id;
    create table feedback (
        id bigint default nextval('feedback_id') primary key, "at" timestamp default current_timestamp, author varchar,
        kind varchar, text varchar, status varchar default 'new', triage json, backlog_id integer, applied_at timestamp);
    """,
    # R11: patterns the owners pressed Forget on; a forgotten pattern is not applied until `until`.
    """
    create table learned_forgotten (pattern varchar primary key, forgotten_at timestamp default current_timestamp, until date);
    """,
    # Console tax P&L: Zerodha's own realised gains per financial year (stage 7 check)
    """
    create table console_pnl_totals (fy varchar, segment varchar, category varchar, profit double, period_end date,
        source_ref varchar, modified varchar, primary key (fy, segment, category));
    create table console_pnl (fy varchar, segment varchar, category varchar, symbol varchar, isin varchar,
        quantity double, buy_value double, sell_value double, realised double, source_ref varchar);
    """,
    # R13: the fund forecaster. fund_base_rates is measured on the AMFI NAVs (group x quartile of the 3-year peer rank);
    # fund_calls is a sibling of calls for fund calls, scored against the category's middle fund from NAVs.
    """
    create table fund_base_rates (horizon_days integer, group_name varchar, quartile integer, n integer, periods integer,
        hit_rate double, avg_excess double, cost_drag double, computed_on date,
        primary key (horizon_days, group_name, quartile));
    create sequence fund_call_id;
    create table fund_calls (
        id bigint default nextval('fund_call_id') primary key, made_on date, isin varchar, scheme_code integer, name varchar,
        category varchar, call varchar, code_call varchar, model_stance varchar, probability double, base_rate double,
        base_rate_n integer, line varchar, detail json, nav double, compare_code integer, runner varchar,
        score_1m double, score_3m double, score_6m double);
    """,
    # R16: one-time cleanup of `problems` from before the journal merged repeats. Unresolved duplicates (same job and key) become
    # one row (earliest sighting, latest sighting, occurrences added up); resolved rows older than 30 days go; anything
    # unresolved stays. Safe to run twice: a second run finds nothing to merge or drop.
    """
    update problems set count = g.total, seen_at = g.first_seen, last_seen = g.last_seen
    from (select max(id) as keep_id, sum(coalesce(count, 1)) as total, min(seen_at) as first_seen,
                 max(coalesce(last_seen, seen_at)) as last_seen
          from problems where resolution is null group by job, coalesce(key, message) having count(*) > 1) g
    where problems.id = g.keep_id;
    delete from problems where resolution is null and id not in
        (select max(id) from problems where resolution is null group by job, coalesce(key, message));
    delete from problems where resolution is not null and coalesce(last_seen, seen_at) < current_timestamp - interval 30 day;
    """,
    # R18: income tax return documents (one row per Drive file) and Fidelity statement events (vests, sales, 1042-S),
    # held against Console and the lots by the stage 7 checks
    """
    create table itr_documents (ref varchar primary key, kind varchar, assessment_year varchar, fy varchar, form varchar,
        filed_on date, for_owner boolean, fa_present boolean, fa_entries integer, modified varchar,
        total_income double, tax_payable double, interest_fees double, taxes_paid double, refund double,
        balance_due double, capital_gains_head double, stcg_equity double, stcg_total double, ltcg_equity double,
        ltcg_total double, tds_credited double);
    create table fidelity_events (ref varchar, kind varchar, event_date date, grant_id varchar, quantity double,
        net_quantity double, price_usd double, amount_usd double, acquired_on date, cost_usd double);
    """,
    # R7 (plan M7): site_extras goes. The weekly sections the site shows are read from weekly_reports and reshaped by the site;
    # the fund calls become a weekly report too; tokens come from config at build time; the last feedback summary gets a table.
    """
    create table feedback_changes (built_on date primary key, changes json);
    insert into feedback_changes select built_on, body from site_extras where name = 'feedback_changes';
    insert or replace into weekly_reports select built_on, 'fund_calls', body from site_extras where name = 'fund_calls';
    drop table site_extras;
    """,
    # Lane C: the gaps ledger. Every empty or partial number records why (the father's screens hide it; Health shows it).
    """
    create table gaps (area varchar, subject varchar, reason varchar, detail varchar, first_seen timestamp default current_timestamp,
        last_seen timestamp default current_timestamp, resolved_at timestamp, primary key (area, subject));
    """,
    # Lane W: "I hold this for years" marks (the dashboard's long_term_mark) and the owners' ask_analyst requests.
    # Not in `trade_tags`: that table is derived and rewritten on every sync, and has no symbol column.
    """
    create table long_term_marks (symbol varchar primary key, marked_by varchar, marked_at timestamp default current_timestamp);
    create sequence analyst_ask_id;
    create table analyst_asks (id bigint default nextval('analyst_ask_id') primary key, symbol varchar, asked_by varchar, asked_on date,
        asked_at timestamp default current_timestamp, status varchar default 'pending', done_at timestamp);
    """,
    # Lane D: promoter holding and pledge per quarter (NSE shareholding master and shareholding XBRL). pledge_pct is the share of
    # the promoter group's own shares that are pledged; null means unknown. pledge_checked: the XBRL has been read (or there is none).
    """
    create table ownership (symbol varchar, quarter_end date, promoter_pct double, public_pct double, pledge_pct double,
        xbrl_url varchar, filed_on date, pledge_checked boolean default false, primary key (symbol, quarter_end));
    """,
    # Lane E: house rules. Owner feedback becomes a proposed edit; an Approve click makes it live (status approved).
    """
    create sequence house_rule_id;
    create table house_rule_edits (id bigint default nextval('house_rule_id') primary key, text varchar, feedback_id bigint,
        status varchar default 'proposed', proposed_at timestamp default current_timestamp, decided_at timestamp);
    """,
    # Lane E: the analyst's answer to an owner's ask is kept on the ask (status done), not in `calls`.
    """
    alter table analyst_asks add column answer json;
    """,
    # Lane V: a price series with an unexplained jump over 40% inside the window the screens and charts read. `sp verify` fills it
    # (and empties it when the jump leaves the window or a corporate action explains it); screens, calls and the site skip these.
    """
    create table price_flags (symbol varchar, jump_date date, move double, kind varchar, close_before double, close_after double,
        flagged_on date, primary key (symbol, jump_date));
    """,
    # P1: a demerger's price factor (close before / close on the ex-date, derived from prices); lots built from
    # Kite's units, not from a document, are marked estimated
    """
    create table demerger_factors (symbol varchar, ex_date date, price_factor double, primary key (symbol, ex_date));
    alter table lots add column estimated boolean default false;
    """,
    # Fidelity's own current Stock Plan page (an owner screenshot): the share count and cost basis the vest documents must reach
    """
    create table fidelity_holdings (as_of date, symbol varchar, isin varchar, quantity double, cost_basis_inr double,
        value_inr double, price_usd double, primary key (as_of, symbol));
    """,
    # Lane R: Fidelity's "Current Shares" export, one row per lot as the statement shows it (cost in rupees as Fidelity converts it)
    """
    create table fidelity_lots (as_of date, symbol varchar, isin varchar, acquired_on date, quantity double, cost_basis_inr double,
        cost_per_share_inr double, value_inr double, gain_inr double, sale_available date, grant_date date, term varchar,
        primary key (as_of, symbol, acquired_on, cost_basis_inr));
    """,
]


class Busy(Exception):
    """Another process holds the writer lock. `holder` is what it wrote: {"job", "pid", "since"} (or None)."""

    def __init__(self, holder: dict | None):
        self.holder = holder
        who = f"{holder.get('job')} (pid {holder.get('pid')}, since {holder.get('since')})" if holder else "another process"
        super().__init__(f"database busy: held by {who}")


LOCK_NAME = "db.lock"
_HELD: dict[str, list] = {}      # lock path -> [fd, users]: opening twice in one process shares the one lock


def _lock_path(path) -> Path:
    return Path(path).parent / LOCK_NAME


def holder(path) -> dict | None:
    """Who holds the writer lock right now, read from the lock file without opening the database.
    None when nobody holds it (a file left by a process that has since died does not count)."""
    lock = _lock_path(path)
    if not lock.exists():
        return None
    fd = os.open(lock, os.O_RDWR)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            try:
                return json.loads(os.pread(fd, 4096, 0) or b"{}") or {"job": "unknown"}
            except ValueError:
                return {"job": "unknown"}
        fcntl.flock(fd, fcntl.LOCK_UN)
        return None
    finally:
        os.close(fd)


def _take(path, job: str, wait_s: float, poll_s: float) -> str:
    lock = _lock_path(path)
    lock.parent.mkdir(parents=True, exist_ok=True)
    key = str(lock.resolve())
    if key in _HELD:
        _HELD[key][1] += 1
        return key
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + wait_s
    while True:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            break
        except BlockingIOError:
            if time.monotonic() >= deadline:
                try:
                    who = json.loads(os.pread(fd, 4096, 0) or b"{}") or None
                except ValueError:
                    who = {"job": "unknown"}
                os.close(fd)
                raise Busy(who) from None
            time.sleep(max(0.0, min(poll_s, deadline - time.monotonic())))
    info = {"job": job, "pid": os.getpid(), "since": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    os.ftruncate(fd, 0)
    os.pwrite(fd, json.dumps(info).encode(), 0)
    _HELD[key] = [fd, 1]
    return key


def _release(key: str) -> None:
    held = _HELD.get(key)
    if not held:
        return
    held[1] -= 1
    if held[1] <= 0:
        del _HELD[key]
        try:
            os.ftruncate(held[0], 0)       # nobody holds it now; the file must not name a holder
        finally:
            os.close(held[0])               # closing drops the flock


class Connection:
    """A DuckDB connection that owns a share of the writer lock: close() gives the lock back.
    Everything else is the DuckDB connection's own."""

    def __init__(self, db, key: str):
        self._db, self._key = db, key

    def __getattr__(self, name):
        return getattr(self._db, name)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    def close(self) -> None:
        key, self._key = self._key, None
        try:
            self._db.close()
        finally:
            if key:
                _release(key)

    def __del__(self):      # dropped without close(): give the lock back; DuckDB closes its own connection
        key, self._key = getattr(self, "_key", None), None
        if key:
            try:
                _release(key)
            except Exception:  # noqa: BLE001 - interpreter shutdown
                pass


# Jobs that run the whole-market screen (a year of prices for ~3,500 stocks) need more than the default 256 MB; found on the VM
# at 237/244 MiB used. The systemd units cap the process at 600 MB, and the connection is closed while the runner and wrangler work.
HEAVY_JOBS = {"daily", "weekly", "ship", "site"}
MEMORY_LIMIT = "256MB"
HEAVY_MEMORY_LIMIT = "420MB"


def open(path: Path | str, *, job: str = "cli", wait_s: float = 0.0,  # noqa: A001 - mirrors file open
         poll_s: float = 5.0) -> Connection:
    """Take the writer lock (waiting up to wait_s, polling every poll_s), then connect and migrate.
    Raises Busy, with the holder, when the lock stays taken."""
    path = Path(path)
    key = _take(path, job, wait_s, poll_s)
    try:
        try:
            raw = duckdb.connect(str(path))
        except duckdb.IOException as err:       # a process that does not use the lock (a shell session) has the file
            if "lock" not in str(err).lower():
                raise
            raise Busy({"job": "outside the lock", "pid": None, "since": None}) from err
        db = Connection(raw, key)
    except BaseException:
        _release(key)
        raise
    try:
        raw.execute("set enable_progress_bar = false")
        raw.execute(f"set memory_limit = '{HEAVY_MEMORY_LIMIT if job in HEAVY_JOBS else MEMORY_LIMIT}'")
        raw.execute("set threads = 2")
        temp = path.parent / "tmp"
        temp.mkdir(parents=True, exist_ok=True)
        raw.execute(f"set temp_directory = '{temp}'")
        raw.execute("set preserve_insertion_order = false")
        raw.execute("create table if not exists schema_migrations (version integer primary key)")
        done = version(raw)
        for number, sql in enumerate(MIGRATIONS[done:], start=done + 1):
            raw.execute("begin")
            raw.execute(sql)
            raw.execute("insert into schema_migrations values (?)", [number])
            raw.execute("commit")
        from stockpilot import journal
        journal.flush_skipped(raw)
    except BaseException:
        db.close()
        raise
    return db


def close(db) -> None:
    """Close the connection and release the writer lock (it also dies with the process)."""
    db.close()


def version(db: duckdb.DuckDBPyConnection) -> int:
    return db.execute("select coalesce(max(version), 0) from schema_migrations").fetchone()[0]
