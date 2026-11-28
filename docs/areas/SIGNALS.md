# Area SIGNALS: nightly screen and calls, lists, today, record

Status: building

## Done
- Contract `contract/src/calls/calls.ts`: the seven verdicts, `CallRow`, `callRowCheck` (chance 5% to 95%, base rate of 30 cases, a horizon, Bengali on every sentence, "limited evidence"), `confidenceLine`, `bucketLimited`, `ScreenRow`, `CallsRun`; datasets `screen` (one file per run) and `calls_runs` in `contract/src/datasets.ts`; job kinds `screen` and `forecast`.
- Calls backend `api/src/calls/` (append-only door `/api/calls/publish`, `/api/calls` latest per stock, `/api/calls/:symbol` history, `/api/calls/compare`, `/api/calls/scored`), migration, `api/drizzle/calls.ts`.
- Jobs `py/stockpilot/jobs/forecast/` (verdict lines, similar-call grouping, English and Kolkata Bengali templates, hold-back rules) and `py/stockpilot/jobs/screen/` (deterministic percentile rank in industry, content-hashed file, counts analysed and passed); workflows `.github/workflows/screen.yml`, `forecast.yml`.
- Lists: contract `contract/src/lists/lists.ts`, dataset `lists`, Job `py/stockpilot/jobs/lists/` (Top 10, Just missed, has our view, falling, busy today; reasons in English and Bengali), duty `api/src/lists/duty.ts` (every 30 minutes in market hours), routes `api/src/lists/routes.ts` (`/api/lists` with the screen's analysed and passed counts, `/api/watchlist` star, `/api/not-now` with Undo, `/api/lists/inputs` for the Job), migration, `api/drizzle/lists.ts`, `.github/workflows/lists.yml`.
- Record: contract `contract/src/record/record.ts`, dataset `record_runs`, Job `py/stockpilot/jobs/record/` (scores ended calls against the Nifty, three returns kept per score), routes `api/src/record/routes.ts` (`/api/record` track record with Brier against the base rate, calibration, adding value; Job doors `/api/record/inputs`, `/api/record/scores`), `.github/workflows/record.yml`.
- Today: `money/src/callline/callline.ts` (the one call-line function; exported from `money/src/index.ts`), contract `contract/src/today/today.ts`, dataset `market`, Job `py/stockpilot/jobs/market/` (Nifty trend, breadth among the 500 largest, value band from the middle P/E; Bengali sentences), `api/src/today/routes.ts` (`/api/today`: call line, money left, market health, groups by verdict, stale holdings), `.github/workflows/market.yml`.
- Checks: C-025-4, C-027-2.py, C-049-3, C-049-4.py (lists data), C-052-1, C-053-1, C-087-1, C-087-3 (Worker side), C-088-1, C-031-1, C-035-1, C-170-1 (+ `C-170-2.py` screen, `C-170-3.py` Job), C-171-1, C-034-1.

## Next
- [ ] Smallcase against our trades (C-091-1): port the v2 comparison (`py/stockpilot/book/smallcase.py`) into `money/src/record/` as a pure function over the pairs MONEY already has; check from fixtures.
- [ ] Today: "Unusual today" group (fed by the lists' busy today rows); production check C-025-3 (every holding has a call dated after the last trading day) reads `stale_held` from `/api/today`.
- [ ] `tools/migrate/calls.ts`, `lists.ts`, `record.ts`: v2's calls, watchlist, Not now rows and track record (see how other areas wrote theirs).
- [ ] Wire the call line into the email feed (NEWS notebook lists it as waiting on `money/src/callline/`).
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

- Record: call_scores has the three returns per call; adding value is averaged in SQL on read, so it counts every scored Buy call, not just the night's. The equal-weight watchlist is read by the Job from the Worker and only returns (never symbols) are stored or logged.
- Nifty history for scoring comes from yfinance in the Job (the Worker holds none).
- Added `lists` duty to `checks/C-116-3.test.ts` (shared check, as NEWS did for `news`); `lists.yml`, `record.yml` to `checks/MOVE-2.py`.
- A star holds a stock (symbol) or a fund (ISIN) in one `watchlist` table; Un-star is a DELETE, Undo of it is a second star. Not now rows end by their `until` time on read; Undo deletes the row.
- Busy today uses the quotes we already hold (a move of 3% or more from yesterday's close), since the cache only holds stocks people asked about; falling is the weakest tenth on the screen's momentum rank.

- Call line: a Sell counts only on a stock held; a Buy needs money left (or no budget set) and is dropped for Not now stocks. Money left is budget minus this month's stock buys.
- Breadth is among the 500 largest stocks by market cap (one bulk yfinance download), because a whole-market breadth would need every stock's history read from D1 each night; it is empty (null) under 100 stocks.
- Value band edges 18 and 24 on the middle P/E are mine (cheap, fair, dear); change in `VALUE_BAND_EDGES` and the Job together.
- `money/src/index.ts` got one export line for `callline` (shared file).

## Blocked
- cockpit: `_job.yml` has no step that uploads a file-delivery run's file (`out/data/screen.<hash>.json`) to the `data` release, so the screen file is not yet served at `/data/<name>`.
- private run: none


Chapter end: 1
