# Area SIGNALS: nightly screen and calls, lists, today, record

Status: building

## Done
- Contract `contract/src/calls/calls.ts`: the seven verdicts, `CallRow`, `callRowCheck` (chance 5% to 95%, base rate of 30 cases, a horizon, Bengali on every sentence, "limited evidence"), `confidenceLine`, `bucketLimited`, `ScreenRow`, `CallsRun`; datasets `screen` (one file per run) and `calls_runs` in `contract/src/datasets.ts`; job kinds `screen` and `forecast`.
- Calls backend `api/src/calls/` (append-only door `/api/calls/publish`, `/api/calls` latest per stock, `/api/calls/:symbol` history, `/api/calls/compare`, `/api/calls/scored`), migration, `api/drizzle/calls.ts`.
- Jobs `py/stockpilot/jobs/forecast/` (verdict lines, similar-call grouping, English and Kolkata Bengali templates, hold-back rules) and `py/stockpilot/jobs/screen/` (deterministic percentile rank in industry, content-hashed file, counts analysed and passed); workflows `.github/workflows/screen.yml`, `forecast.yml`.
- Checks: C-031-1, C-035-1, C-170-1 (+ `C-170-2.py` screen, `C-170-3.py` Job), C-171-1, C-034-1.

## Next
- [ ] Lists Job and routes (#271): `py/stockpilot/jobs/lists/`, `api/src/lists/` (Worth following with reasons and updated times, watchlist, star, Not now with Undo), `lists.yml`; checks C-049-3, C-052-1, C-053-1.
- [ ] Worth following counts: read the `screen` run summary (`analysed`, `passed`) and expose it on a lists route for `panes/worth`.
- [ ] Today (#272): `money/src/callline/` (one pure function, shared with the email), market health Job `py/stockpilot/jobs/market/`, `api/src/today/`, `market.yml`; checks C-025-4, C-027-1 data.
- [ ] Record (#273): scoring Job `py/stockpilot/jobs/record/` writing `call_scores` (the confidence line reads it), adding value against the Nifty and an equal-weight watchlist, Smallcase against our trades; `api/src/record/`, `record.yml`; checks C-087-1, C-088-1, C-091-1.
- [ ] `tools/migrate/calls.ts`, `lists.ts`, `record.ts`: v2's calls, watchlist, Not now rows and track record.
- [ ] Set Status: done when all green.

## Decisions
- Calls have their own signed door like news impact: the shared publish door replaces a dataset every run and calls must accumulate. Call id is `exchange:symbol:day:horizon`; a repeat is ignored.
- The public Job never sees holdings, so it emits Buy, Watch, Hold, Weak, Sell and No view yet only. Trim and a holding's own Sell (stop reached) are added in the browser from `money`; `held` is not in the row.
- Verdict lines: Buy from 57 in 100, Watch from 52, Hold above 40, Weak above 30, Sell below (v2's buy and sell lines kept).
- Base rate and its case count come from the mechanical report's walk-forward test (`hit_rate`, `n_test`); the "moved over 8 points" test compares with `docs/backtest.md` lines like `63 days: 53%` and is skipped when the note is absent (it does not exist yet).
- The call card shows the three-month chance; the six-month one stays in the mechanical file.
- Screen inputs are the mechanical forecast's rank signals (quality, sector value, momentum, low volatility) with the industry from the `facts` dataset; no new data source.
- The Job's run row `calls_runs` exists so the 5-minute tick starts the forecast Job (23:00 IST, trading days); `screen` starts at 22:30.
- Shared files touched, one line each: `contract/src/datasets.ts`, `contract/src/core/jobs.ts`, `checks/MOVE-2.py` (allowed workflows).
- Left out for now: a "would buy at" price (null; the "we would buy if" sentence names the chance line instead).

## Blocked
- cockpit: `_job.yml` has no step that uploads a file-delivery run's file (`out/data/screen.<hash>.json`) to the `data` release, so the screen file is not yet served at `/data/<name>`.
- private run: none

