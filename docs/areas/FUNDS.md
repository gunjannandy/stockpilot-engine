# FUNDS

Status: building

## Done
- Held-fund call (`held_calls`: Add/Keep/Review/No data with the measured chance) and `score_calls` (past published calls scored against the category middle after 12 months): `py/stockpilot/jobs/funds/calls.py`.
- Funds Job: `py/stockpilot/jobs/funds/__init__.py`, workflow `.github/workflows/funds.yml` (allowed in `checks/MOVE-2.py`).
- Dataset `funds` (schemes with stats and NAVs): `contract/src/funds/funds.ts`, registered in `contract/src/datasets.ts`.
- API: `api/src/funds/routes.ts`, migration `api/src/funds/migrations/`, tests `api/src/funds/funds.test.ts`.
- Fund-holdings Job: `py/stockpilot/jobs/fundholdings/`, `.github/workflows/fundholdings.yml`, dataset `fund_holdings` (`contract/src/fundholdings/`, includes pure `fundOverlap` for the browser), routes `/api/fund-holdings` and `/api/fund-holdings/:id` in `api/src/fundholdings/`; checks in its tests (C-076-1).
- Merged main into the branch; the planner-label gate no longer exists in CI, so PR #69's red job is gone.

- Fund calls, public part: `py/stockpilot/jobs/funds/calls.py` (screen, backtested base rate by kind and 3-year quartile, track record), published by the funds Job as dataset `fund_calls` (`contract/src/fundcalls/`, route `GET /api/fund-calls` in `api/src/fundcalls/`, tests beside each).

## Next
- [ ] Confirm `gate` is green on PR #69 and it merges.
- [ ] Find a source each of the 10 houses serves to Actions (`config/fund_house_sources.json` has 5 of 10 unfound); until then they report 'cannot be fetched' in the run's lines.
- [x] Held-fund call and scored-later track record: `held_calls` and `score_calls` in `py/stockpilot/jobs/funds/calls.py` (tests beside). Remaining: the VM caller passes held ids and past published rows to them (private side, outside this repo's data). Was: weekly fund forecast (start: `py/stockpilot/fundcall.py` reads a duckdb `navs` table and the book; the engine's `funds` dataset has weekly NAVs, category middles and ranks, so port its screen/base-rate steps onto those rows; the held-fund part runs privately on the VM; publish a `fund_calls` dataset plus its track record) and call (held, buy, watch) from NAV history, with track record; extend the existing fund call code rather than duplicating it; shapes in `contract/`.
- [x] Fund detail report: see section below.
- [ ] Unit checks: overlap from fixtures, returns/rolling/falls/cost/size from fixtures.

## Fund detail report (issue 283)
Supported today from free data: weekly NAV chart up to 5 years, 1/3/5 year returns, category middle and count, worst fall, rolling 1-year spread and loss share, Direct and Regular yearly cost, size, top-holdings and overlap (fund_holdings, houses we can fetch), and now a buy/watch call with a measured chance.
Free additions still open: SIP-style return over the NAV history, calendar-year returns, up/down capture against the category middle, and holdings-derived concentration (top 10 share, sector from holdings names) once more houses are fetchable.
Not supportable free: exit load, fund manager and tenure, official benchmark and its returns, portfolio turnover, star ratings. Their sources are paid or scraped from pages that block Actions; a screen should leave them out rather than show blanks.

## Decisions
- Kept both sides when main's `feedback` dataset and our `funds` dataset collided in `contract/src/datasets.ts`.
- `fund_holdings` runs nightly: the schedule can only say trading days or every day; the Job is cheap and republishes the same month.
- `fund_holdings` is private visibility because the registry rule (C-203-1) makes anything named like holdings private.
- Overlap is computed in the browser; the route serves public fund portfolios only.
- Shapes live in `contract/`; no `web/` edits.

- `fund_calls` is built inside the funds Job from the rows it just read (no new workflow, no cross-dataset read); public visibility because it holds no holdings.
- Track record is a backtest on the weekly NAVs (only funds alive today, caveat carried in every row), until real past calls exist to score.
- `held_calls` takes held ids from the caller and stores nothing, so no holdings reach the public engine; it uses the same screen and base rate as Buy/Watch rather than fundcall.py's heavier flow (switch costs, tax and model view stay on the VM).
- Buy needs top quarter on 3 years, last year above category middle, at most 15% of rolling years lost, size 500 crore+, cost known; otherwise Watch.

## Blocked
- Nothing yet.

Chapter end: 3
