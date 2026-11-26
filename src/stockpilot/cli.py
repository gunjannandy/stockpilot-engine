"""`sp`: the one command line for stockpilot. Each subcommand is a thin call into a module."""
import argparse
import subprocess
import sys
from pathlib import Path

from datetime import date, timedelta

from stockpilot import config, journal, store, vault, watchlist

from stockpilot.analysis import backtest

from stockpilot.sources import funds, http, marketdata, nse_api, universe


def _remote_url(cfg) -> str:
    name = cfg.get("vault.remote", "origin")
    return subprocess.run(["git", "remote", "get-url", name], cwd=cfg.root,
                          capture_output=True, text=True, check=True).stdout.strip()


def cmd_vault(args, cfg):
    keys_dir = cfg.root / "config"
    if args.action == "init":
        if (keys_dir / "vault.pub").exists():
            print("Vault keys already exist in config/; not replacing them.")
            return
        vault.create_keys(cfg.require("VAULT_PASSWORD")["VAULT_PASSWORD"]).save(keys_dir)
        print("Vault keys created in config/. Commit vault.pub and vault-identity.age.")
    elif args.action == "push":
        keys = vault.Keys.load(keys_dir)
        vault.push(cfg.root, _remote_url(cfg), keys, cfg.get("vault.paths", ["private", ".env"]))
        print("Vault pushed.")
    elif args.action == "rekey":
        env = cfg.require("VAULT_PASSWORD", "VAULT_PASSWORD_NEW")
        keys = vault.rekey(_remote_url(cfg), env["VAULT_PASSWORD"], env["VAULT_PASSWORD_NEW"],
                           cfg.get("vault.paths", ["private", ".env"]))
        keys.save(keys_dir)
        print("Vault re-locked: only the new password opens it. config/vault.pub and vault-identity.age are new: commit them, "
              "set VAULT_PASSWORD to the new password in .env, then run `sp backup market` so that backup uses the new key.")
    else:
        password = cfg.require("VAULT_PASSWORD")["VAULT_PASSWORD"]
        vault.restore(_remote_url(cfg), password, Path(args.dest))
        print(f"Vault restored into {args.dest}.")


def cmd_migrate_v2(args, cfg):
    """Copy every v1 record into the v2 stores and prove the counts (`--verify-only` checks an earlier copy again)."""
    from stockpilot import migrate_v2
    db = store.open(_db_path(cfg))
    out = cfg.root / "private" / "v2"
    report = migrate_v2.verify(db, out) if args.verify_only else migrate_v2.migrate(db, out)
    for name, t in report["types"].items():
        print(f"{name}: v1 {t['v1']} = v2 {t['v2']}")
    print("All counts and checksums match." if report["ok"] else "MISMATCH")


def _db_path(cfg) -> Path:
    return cfg.root / cfg.get("store.path", "data/stockpilot.duckdb")


def _keys(cfg):
    return vault.Keys.load(cfg.root / "config")


def publish_default_deny():
    from stockpilot import publish
    return publish.DEFAULT_DENY_FILE


def cmd_publish(args, cfg):
    """Copy the code to the public engine repo after the privacy scan (the VM runs it after a merge to main)."""
    from stockpilot import publish
    try:
        pushed = publish.run(cfg.root, remote=args.remote, deny_file=args.deny_file, message=args.message, ref=args.ref)
    except publish.Blocked as err:
        print(f"publish blocked: {err}", file=sys.stderr)
        for f in err.findings:
            print(f"  {f.path}:{f.line} {f.rule}", file=sys.stderr)
        return 1
    print("Published a new snapshot." if pushed else "Nothing changed; nothing published.")


def cmd_vm_jobs(args, cfg):
    """One timer firing of the VM job runner: requests on branch vm-jobs in, results out (never inside a daemon)."""
    from stockpilot.jobs import ship, vmjobs
    queue = Path(args.queue) if args.queue else Path.home() / ".cache" / "stockpilot-vm-jobs" / "queue"
    runner = vmjobs.Runner(root=cfg.root, queue=queue, sp=[str(cfg.root / ".venv" / "bin" / "sp"), "--root", str(cfg.root)],
                           wrangler=ship.wrangler_path(), dry_run=args.dry_run)
    done = runner.poll()
    for res in done:
        print(f"{res['id']}: {res['status']}" + (f" (exit {res['exit']})" if res.get("exit") else ""))
        for line in res.get("would_run", []):
            print(f"  would run: {line}")
    if not done:
        print("No job to run.")
    return 0


def cmd_minute(args, cfg):
    """One firing of the one-minute check (ticket V1). The timer runs `python -m stockpilot.jobs.minute` to skip this module's imports."""
    from stockpilot.jobs import minute
    return minute.run(cfg)


def cmd_backup(args, cfg):
    from stockpilot import backup
    state_dir = cfg.root / "private" / "state"
    db = store.open(_db_path(cfg))
    if args.action == "state":
        print("State saved:", backup.export_state(db, state_dir))
    elif args.action == "load-state":
        print("State loaded:", backup.load_state(db, state_dir))
    elif args.action == "market":
        recipient, upload = None, backup.gh_upload
        if not args.recipient_env:
            recipient = _keys(cfg).recipient
        else:        # a snapshot for the cloud lanes: its own key and its own release, never the vault's
            from pyrage import x25519
            recipient = cfg.require(args.recipient_env)[args.recipient_env]
            try:
                x25519.Recipient.from_str(recipient)
            except Exception as err:  # noqa: BLE001 - never echo the value
                raise SystemExit(f"{args.recipient_env} in .env is not an age public key (it should start with age1).") from err
        if args.tag:
            upload = lambda _tag, files: backup.gh_upload(args.tag, files)      # noqa: E731
        print("Market data uploaded:", backup.backup_market(db, recipient, upload))
    elif args.action == "nightly":
        print("Nightly backup pushed:", backup.nightly(db, cfg.root, _remote_url(cfg), _keys(cfg), cfg.get("vault.paths")))
    elif args.action == "prove":
        import tempfile
        password = cfg.require("VAULT_PASSWORD")["VAULT_PASSWORD"]
        print("Restore proof:", backup.prove_restore(_remote_url(cfg), password, Path(tempfile.mkdtemp(prefix="sp-prove-"))))
    else:
        password = cfg.require("VAULT_PASSWORD")["VAULT_PASSWORD"]
        print("Market data restored:", backup.restore_market(db, _keys(cfg).sealed_identity, password,
                                                             backup.gh_download))


def cmd_init_db(args, cfg):
    db = store.open(cfg.root / cfg.get("store.path", "data/stockpilot.duckdb"))
    print(f"Store ready at schema version {store.version(db)}.")


def cmd_prices(args, cfg):
    db = store.open(cfg.root / cfg.get("store.path", "data/stockpilot.duckdb"))
    day, end, total = date.fromisoformat(args.start), date.fromisoformat(args.end or args.start), 0
    while day <= end:
        if day.weekday() < 5:
            if args.indices_only:
                n = marketdata.ingest_index_closes(db, day, http.fetch)
            else:
                n = marketdata.ingest_nse_bhavcopy(db, day, http.fetch)
            total += n
            print(f"{day}: {n} rows" if n else f"{day}: no file (holiday?)", flush=True)
        day += timedelta(days=1)
    print(f"Done: {total} rows.")


def cmd_watchlist(args, cfg):
    db = store.open(cfg.root / cfg.get("store.path", "data/stockpilot.duckdb"))
    if args.action == "import":
        print(f"Added {watchlist.import_csv(db, args.path)} symbols.")
    else:
        for symbol, exchange in watchlist.active(db):
            print(f"{symbol}\t{exchange}")


# How long each timed job waits for the database before it gives up and records `skipped`, in seconds.
WAITS = {"tick": 5 * 60, "daily": 45 * 60, "ship": 30 * 60, "nav": 30 * 60, "weekly": 60 * 60, "kite": 10 * 60, "queue": 0, "redeploy": 5 * 60, "doctor": 0, "ownership": 30 * 60}
EX_TEMPFAIL = 75      # busy, or the day's source is not out yet: not a fault, try again


def _db(cfg, job: str = "cli"):
    return store.open(_db_path(cfg), job=job, wait_s=WAITS.get(job, 0))


def _machine(cfg, job: str = "tick"):
    from stockpilot import machine
    m = machine.real(cfg)
    m.wait_s = WAITS.get(job, 0)
    return m


def _now(args):
    from datetime import datetime
    day = getattr(args, "date", None)
    return datetime.combine(date.fromisoformat(day), datetime.now().time()) if day else datetime.now()


def cmd_tick(args, cfg):
    """The one timed command: the queue, then at most one due job."""
    from stockpilot.jobs import tick
    report = tick.run(_machine(cfg, "tick"))
    print(report)
    return tick.exit_code(report)


def cmd_redeploy(args, cfg):
    """The v2 site deploy timer: daily slots and a change on main; hard blocks and rollback inside the deploy."""
    from stockpilot.jobs import redeploy
    report = redeploy.run(_machine(cfg, "redeploy"))
    print(report)
    return redeploy.exit_code(report)


def cmd_daily(args, cfg):
    """The whole evening job now (a manual rerun): ingest, Kite, documents, calls, ship."""
    from stockpilot.jobs import daily
    report = daily.run(_machine(cfg, "daily"), _now(args), force=True)
    print(report)
    return {"holiday": 0, "ok": 0, "partial": 0, "waiting": EX_TEMPFAIL}.get(report["status"], 2)


def cmd_analyst_asks(args, cfg):
    """Answer the owners' pending "Ask the analyst" requests now (the evening crunch does this every day before ship)."""
    from stockpilot.jobs import daily
    m = _machine(cfg, "daily")
    db = store.open(_db_path(cfg), job="asks", wait_s=WAITS.get("daily", 0))
    try:
        print(daily.run_asks(m, db, _now(args).date()))
    finally:
        store.close(db)
    return 0


def cmd_house_rules(args, cfg):
    """List the house rules (the base file and the approved lines); `--retire ID` takes an approved line off."""
    from stockpilot import house_rules
    db = store.open(_db_path(cfg), job="house-rules", wait_s=WAITS.get("daily", 0))
    try:
        if args.retire is not None:
            print("retired" if house_rules.retire(db, args.retire) else "no such live rule")
        else:
            print(house_rules.base())
            for i, text, status in db.execute("select id, text, status from house_rule_edits order by id").fetchall():
                print(f"[{i}] {status}: {text}")
    finally:
        store.close(db)
    return 0


def cmd_feedback_triage(args, cfg):
    """Route the owners' new feedback now (the evening crunch does this every day after ship)."""
    from stockpilot.jobs import daily
    m = _machine(cfg, "daily")
    db = store.open(_db_path(cfg), job="feedback", wait_s=WAITS.get("daily", 0))
    try:
        print(daily.run_feedback(m, db, _now(args)))
    finally:
        store.close(db)
    return 0


def cmd_stocks(args, cfg):
    print(f"Stocks listed: {universe.refresh_stocks(_db(cfg), http.fetch)}")


def cmd_backtest(args, cfg):
    db = _db(cfg)
    rates = backtest.base_rates(db, date.fromisoformat(args.start), date.fromisoformat(args.end),
                                horizon_days=args.horizon, step_days=args.step)
    backtest.save(db, rates, args.horizon, date.today())
    for key in sorted(rates):
        v = rates[key]
        print(f"{key}: n={v['n']} hit={v['hit_rate']:.2%} excess={v['avg_excess']:+.2%}")


def cmd_corporate_actions(args, cfg):
    from stockpilot.trades import corporate_actions, corporate_actions_feeds
    db = _db(cfg)
    fetch_json = nse_api.Session().fetch_json
    n = corporate_actions.backfill(db, fetch_json, date.fromisoformat(args.since), date.today())
    n += corporate_actions_feeds.backfill(db, fetch_json, date.fromisoformat(args.since), date.today())
    print(f"{n} splits and bonuses stored from NSE.")
    if args.fallback_yfinance:
        n = corporate_actions.fallback_yfinance(db, corporate_actions.yfinance_splits,
                                                cfg.get("universe.liquidity_floor_cr", 1.0),
                                                date.fromisoformat(args.since))
        print(f"{n} splits stored from yfinance for jumps NSE did not list.")


def cmd_filings(args, cfg):
    """Quarterly results history from NSE filings. `backfill` is resumable: run it again after any stop."""
    from stockpilot.sources import filings
    db, today = _db(cfg), date.today()
    fetch_json, fetch_file = filings.fetchers(nse_api.Session())
    symbols = args.symbols or filings.symbols_to_load(db, today, args.floor)
    run = filings.backfill if args.action == "backfill" else filings.refresh
    print(f"{len(symbols)} symbols", flush=True)
    print(run(db, fetch_json, fetch_file, symbols, today))


def cmd_navs_history(args, cfg):
    """Five years of NAVs for the held funds and their peers. Resumable: run it again after any stop."""
    from stockpilot.sources import navhistory as nh
    db, today = _db(cfg), date.today()
    if args.probe:
        print(nh.probe(nh.open_lines, today))
        return
    codes = nh.scope(db)
    print(f"{len(codes)} schemes in scope", flush=True)
    print(nh.backfill(db, nh.open_lines, nh.fetch_json, today, window_days=args.window_days, codes=codes))


def cmd_quality(args, cfg):
    from stockpilot.analysis import quality
    print(quality.write_report(_db(cfg), Path(cfg.root) / "data" / "quality.md"))


def cmd_fundamentals(args, cfg):
    import time
    from stockpilot.sources import fundamentals
    db, today = _db(cfg), date.today()
    symbols = args.symbols or fundamentals.pool(db, today, args.floor)
    print(f"{len(symbols)} symbols", flush=True)
    missing = []
    for i, symbol in enumerate(symbols, 1):
        missing += fundamentals.refresh(db, [symbol], today, fundamentals.yahoo)["missing"]
        if i % 25 == 0:
            print(f"{i}/{len(symbols)} done, {len(missing)} missing", flush=True)
        time.sleep(args.pause)
    print(f"Stored {len(symbols) - len(missing)}; missing {len(missing)}: {' '.join(missing)}")


def cmd_nav(args, cfg):
    from stockpilot.jobs import nav
    out = nav.run(_machine(cfg, "nav"), _now(args))
    print(out)
    return 0 if out["status"] == "ok" else 2


def cmd_ownership(args, cfg):
    from stockpilot.jobs import ownership
    out = ownership.run(_machine(cfg, "ownership"), _now(args))
    print(out)
    return 0 if out["status"] == "ok" else 2


def cmd_kite(args, cfg):
    from stockpilot.jobs import daily, ship
    m = _machine(cfg, "kite")
    with m.db("kite") as db:
        out = daily.run_kite(db, m.worker or _no_worker(cfg))
        print(out)
        if out["status"] == "ok" and not getattr(args, "no_publish", False):   # the owner just logged in: show it now
            try:
                print(ship.publish(m, db))
            except RuntimeError as err:
                print(err, file=sys.stderr)
                return 2
    return {"login_needed": 3, "failed": 2}.get(out["status"], 0)


def _no_worker(cfg):
    cfg.require("SP_VM_KEY")


def cmd_queue(args, cfg):
    from stockpilot.jobs import queue
    print(queue.run(_machine(cfg, "queue")))


def cmd_build_site(args, cfg):
    from stockpilot.jobs import ship
    with _db(cfg, "site") as db:
        meta = ship.build_site(db, cfg, args.out)
    print(f"Site built in {args.out}/ (prices as of {meta['as_of']}).")


def cmd_verify(args, cfg):
    from stockpilot.verify import run as verify_run
    return verify_run.run(cfg, db_path=_db_path(cfg), site=args.site or cfg.root / "site", previous=args.previous, briefs=args.briefs,
                          day=date.fromisoformat(args.day) if args.day else None, read_only=args.read_only,
                          issues=not args.no_issues, only={int(n) for n in args.only.split(",")} if args.only else None,
                          rerun_backtest=args.rerun_backtest, report_dir=args.report_dir, as_json=args.json)


def cmd_trades(args, cfg):
    from stockpilot.jobs import docs
    from stockpilot.trades import lots, tradebook
    db = _db(cfg)
    if args.action == "import":
        added = lots.save_trades(db, tradebook.parse(Path(args.path).read_text(encoding="utf-8-sig")))
        print(f"Tradebook: {added} new trades.")
    elif args.action == "fidelity-lots":
        from stockpilot.trades import fidelity_lots
        if not args.path or not args.as_of:
            raise SystemExit("usage: sp trades fidelity-lots <Current Shares pdf> --as-of YYYY-MM-DD (the statement's own date)")
        got = fidelity_lots.ingest(db, Path(args.path).read_bytes(), date.fromisoformat(args.as_of))
        print(f"Fidelity lots: {got.note} {got.stored} new." if got.consistent else f"Fidelity lots not stored: {got.note}")
    elif args.action == "sync":
        bridge, pan = docs.bridge_from(cfg)
        print(docs.sync_docs(db, bridge, pan, since=args.since))
        return
    outcome = lots.rebuild(db)
    print(f"Lots rebuilt: {outcome.lots}.")
    for isin, day, qty in outcome.unmatched_sells:
        print(f"  sell with no lot to match: {isin} {day} {qty:g} (baseline tradebook incomplete?)")
    as_of, gaps = lots.check_against_statement(db)
    for isin, held, ours in gaps:
        print(f"  {isin}: depository statement of {as_of} shows {held:g}, lots hold {ours:g}")


def cmd_weekly(args, cfg):
    """The Saturday review now: every step, batch after batch, then the analysis."""
    from stockpilot.jobs import weekly
    m = _machine(cfg, "weekly")
    while True:
        out = weekly.run(m, _now(args), force=False, analyse_only=args.analyse_only)
        print(out, flush=True)
        if out.get("status") != "more":
            return 0 if out["status"] == "ok" else 2


def cmd_score(args, cfg):
    from stockpilot.calls import record
    with _db(cfg) as db:
        print(f"Scored {record.score(db, date.today())} call windows.")


def cmd_ship(args, cfg):
    """Score old calls, build the site, publish status and the archive, deploy: the end of the daily job, on its own."""
    from datetime import datetime
    from stockpilot.jobs import ship
    m = _machine(cfg, "ship")
    with m.db("ship") as db:
        print(ship.ship(m, db, datetime.now()))


def cmd_doctor(args, cfg):
    from stockpilot.jobs import doctor
    if args.drill:                    # a planted fault in a scratch store; the live one is never opened
        results = doctor.drill(cfg.root, live_db=_db_path(cfg))
        for r in results:
            print(f"{'PASS' if r['ok'] else 'FAIL'}  {r['step']}: {r['detail']}")
        return 0 if all(r["ok"] for r in results) else 1
    m = _machine(cfg, "doctor")
    out = doctor.run(m, push=not args.no_push, reruns=not args.no_reruns)
    if "busy" in out:
        print(f"Doctor: database busy ({out['busy']}); heartbeat {'' if out['heartbeat'] else 'not '}pushed.")
    else:
        print(f"Doctor: {out['opened']} issue(s) opened, {out['reruns']} rerun(s) started.")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="sp", description="stockpilot")
    parser.add_argument("--root", default=".", help="project root (default: current directory)")
    sub = parser.add_subparsers(dest="command", required=True)
    v = sub.add_parser("vault", help="push or restore the encrypted vault")
    v.add_argument("action", choices=["init", "push", "restore", "rekey"])
    v.add_argument("--dest", default="restored", help="where restore unpacks to")
    v.set_defaults(func=cmd_vault)
    bk = sub.add_parser("backup", help="back up the database, encrypted: owner state, or market data")
    bk.add_argument("action", choices=["state", "load-state", "market", "restore-market", "nightly", "prove"])
    bk.add_argument("--tag", help="market: upload to this GitHub release instead of the backup's (the cloud snapshot)")
    bk.add_argument("--recipient-env", help="market: the .env name of the age public key to encrypt to, instead of the vault's")
    bk.set_defaults(func=cmd_backup)
    mg = sub.add_parser("migrate-v2", help="copy every v1 record into the v2 stores and check the counts")
    mg.add_argument("--verify-only", action="store_true", help="check an earlier copy against v1 again")
    mg.set_defaults(func=cmd_migrate_v2)
    pb = sub.add_parser("publish", help="copy the code to the public engine repo, after the privacy scan")
    pb.add_argument("--remote", default="https://github.com/gunjannandy/stockpilot-engine.git", help="the public repo's git URL")
    pb.add_argument("--deny-file", default=publish_default_deny(), help="private list of names that must never leave (default: data/publish-deny.txt)")
    pb.add_argument("--message", default="code copy")
    pb.add_argument("--ref", help="publish this commit (for example origin/main) instead of the working tree")
    pb.set_defaults(func=cmd_publish)
    vj = sub.add_parser("vm-jobs", help="one firing of the VM job runner: requests on branch vm-jobs in, results out")
    vj.add_argument("--dry-run", action="store_true", help="list what would run; run and push nothing")
    vj.add_argument("--queue", help="where the runner keeps its clone of branch vm-jobs")
    vj.set_defaults(func=cmd_vm_jobs)
    sub.add_parser("minute", help="one firing of the one-minute check: model jobs, GitHub starts, stale alarm").set_defaults(func=cmd_minute)
    sub.add_parser("init-db", help="create or migrate the store").set_defaults(func=cmd_init_db)
    p = sub.add_parser("prices", help="ingest NSE bhavcopy for a day or a range")
    p.add_argument("start", help="YYYY-MM-DD")
    p.add_argument("end", nargs="?", help="YYYY-MM-DD (default: start)")
    p.add_argument("--indices-only", action="store_true", help="ingest NSE index closes instead of prices")
    p.set_defaults(func=cmd_prices)
    w = sub.add_parser("watchlist", help="list the watchlist or import a CSV")
    w.add_argument("action", choices=["list", "import"])
    w.add_argument("path", nargs="?")
    w.set_defaults(func=cmd_watchlist)
    sub.add_parser("tick", help="every 10 minutes: the queue, then the one job that is due").set_defaults(func=cmd_tick)
    sub.add_parser("redeploy", help="v2 site deploy timer: daily slots and changes on main, hard blocks and rollback").set_defaults(func=cmd_redeploy)
    d = sub.add_parser("daily", help="the whole evening job now: ingest, Kite, documents, calls, ship")
    d.add_argument("--date", help="YYYY-MM-DD (default: today)")
    d.set_defaults(func=cmd_daily)
    nv = sub.add_parser("nav", help="ingest AMFI NAVs and rebuild the page")
    nv.add_argument("--date", help="YYYY-MM-DD (default: today)")
    nv.set_defaults(func=cmd_nav)
    ow = sub.add_parser("ownership", help="promoter holding and pledge for the held, watched and called stocks (NSE shareholding)")
    ow.add_argument("--date", help="YYYY-MM-DD (default: today)")
    ow.set_defaults(func=cmd_ownership)
    c = sub.add_parser("corporate-actions", help="backfill NSE splits and bonuses, month by month (resumable)")
    c.add_argument("--since", default="2015-01-01", help="YYYY-MM-DD (default: 2015-01-01)")
    c.add_argument("--fallback-yfinance", action="store_true",
                   help="then ask yfinance about liquid stocks with a jump over 40% and no action")
    c.set_defaults(func=cmd_corporate_actions)
    fl = sub.add_parser("filings", help="quarterly results history from NSE filings (backfill is resumable)")
    fl.add_argument("action", choices=["backfill", "refresh"])
    fl.add_argument("--symbols", nargs="*", help="only these symbols (default: holdings, watchlist, liquid pool)")
    fl.add_argument("--floor", type=float, default=1.0, help="liquidity floor, crore a day")
    fl.set_defaults(func=cmd_filings)
    nhp = sub.add_parser("navs-history", help="backfill 5 years of NAVs for held funds and their peers (resumable)")
    nhp.add_argument("--window-days", type=int, default=45, help="days per AMFI request (it shrinks if AMFI refuses)")
    nhp.add_argument("--probe", action="store_true", help="only test which window sizes AMFI accepts")
    nhp.set_defaults(func=cmd_navs_history)
    sub.add_parser("quality", help="write data/quality.md: gaps, stale symbols, jumps").set_defaults(func=cmd_quality)
    b = sub.add_parser("backtest", help="compute base rates from price history")
    b.add_argument("start")
    b.add_argument("end")
    b.add_argument("--horizon", type=int, default=91)
    b.add_argument("--step", type=int, default=28)
    b.set_defaults(func=cmd_backtest)
    f = sub.add_parser("fundamentals", help="refresh Yahoo fundamentals for the liquid pool plus the watchlist")
    f.add_argument("symbols", nargs="*", help="only these symbols (default: the pool)")
    f.add_argument("--floor", type=float, default=1.0, help="liquidity floor, crore a day")
    f.add_argument("--pause", type=float, default=0.5, help="seconds between symbols")
    f.set_defaults(func=cmd_fundamentals)
    wk = sub.add_parser("weekly", help="fund review, opportunities, allocation and tax (Saturday)")
    wk.add_argument("--date", help="YYYY-MM-DD (default: today)")
    wk.add_argument("--analyse-only", action="store_true", help="skip the network refresh and use stored data")
    wk.set_defaults(func=cmd_weekly)
    sub.add_parser("stocks", help="refresh names, ISINs and industries").set_defaults(func=cmd_stocks)
    kt = sub.add_parser("kite", help="read the day's Kite data through the Worker; snapshot, reconcile, publish")
    kt.add_argument("--no-publish", action="store_true", help="skip the site rebuild (the daily job publishes itself)")
    kt.set_defaults(func=cmd_kite)
    sub.add_parser("queue", help="apply the dashboard's pending requests").set_defaults(func=cmd_queue)
    bs = sub.add_parser("build-site", help="write the static dashboard from the store")
    bs.add_argument("--out", default="site", help="output folder (default: site)")
    bs.set_defaults(func=cmd_build_site)
    vf = sub.add_parser("verify", help="check the data and the forecast; non-zero exit on any hard failure (the deploy gate)")
    vf.add_argument("--site", help="built site folder to check (default: site)")
    vf.add_argument("--previous", help="yesterday's built site, checked against the same contract")
    vf.add_argument("--briefs", help="folder of the analyst briefs (default: data/briefs)")
    vf.add_argument("--day", help="YYYY-MM-DD (default: today)")
    vf.add_argument("--only", help="comma list of check numbers, for example 1,3")
    vf.add_argument("--json", action="store_true", help="print the result as JSON instead of the one-line summary")
    vf.add_argument("--read-only", action="store_true", help="do not write price flags or gaps (the store stays untouched)")
    vf.add_argument("--no-issues", action="store_true", help="do not open GitHub issues")
    vf.add_argument("--rerun-backtest", action="store_true", help="check 8 re-runs the backtest on the latest prices (about 12 minutes)")
    vf.add_argument("--report-dir", help="where verify-<date>.md goes (default: docs/status)")
    vf.set_defaults(func=cmd_verify)
    t = sub.add_parser("trades", help="load the tradebook or sync broker emails, then rebuild lots")
    t.add_argument("action", choices=["import", "sync", "rebuild", "fidelity-lots"])
    t.add_argument("path", nargs="?", help="tradebook CSV (import) or the Current Shares PDF (fidelity-lots)")
    t.add_argument("--as-of", help="fidelity-lots: the statement's own date")
    t.add_argument("--since", help="ISO timestamp (sync; default: everything)")
    t.set_defaults(func=cmd_trades)
    sub.add_parser("score", help="score calls whose 1, 3 or 6 months ended").set_defaults(func=cmd_score)
    sub.add_parser("analyst-asks", help="answer pending 'Ask the analyst' requests now").set_defaults(func=cmd_analyst_asks)
    hr = sub.add_parser("house-rules", help="list the analyst's house rules, or retire an approved one")
    hr.add_argument("--retire", type=int, metavar="ID")
    hr.set_defaults(func=cmd_house_rules)
    sub.add_parser("feedback-triage", help="route new owner feedback into issues now").set_defaults(func=cmd_feedback_triage)
    sub.add_parser("ship", help="score, archive and publish status (runs after sp daily)").set_defaults(func=cmd_ship)
    dr = sub.add_parser("doctor", help="check health, open self-heal issues, publish status")
    dr.add_argument("--no-push", action="store_true", help="do not push status.json")
    dr.add_argument("--no-reruns", action="store_true", help="do not act on rerun-requested issues")
    dr.add_argument("--drill", action="store_true", help="fire drill: plant a fault in a scratch copy and check the whole path")
    dr.set_defaults(func=cmd_doctor)
    args = parser.parse_args(argv)
    cfg = config.load(args.root)
    try:
        return args.func(args, cfg) or 0
    except (config.MissingSecrets, vault.VaultError) as err:
        print(err, file=sys.stderr)
        return 1
    except store.Busy as err:
        journal.record_skipped(_db_path(cfg).parent, args.command, err.holder)
        print(f"{args.command}: {err}. Recorded as skipped.", file=sys.stderr)
        return 0 if args.command in ("queue", "doctor") else EX_TEMPFAIL


if __name__ == "__main__":
    sys.exit(main())
