# FUNDS

Status: building

## Done
- Funds Job: `py/stockpilot/jobs/funds/__init__.py`, workflow `.github/workflows/funds.yml` (allowed in `checks/MOVE-2.py`).
- Dataset `funds` (schemes with stats and NAVs): `contract/src/funds/funds.ts`, registered in `contract/src/datasets.ts`.
- API: `api/src/funds/routes.ts`, migration `api/src/funds/migrations/`, tests `api/src/funds/funds.test.ts`.
- Fund-holdings Job: `py/stockpilot/jobs/fundholdings/`, `.github/workflows/fundholdings.yml`, dataset `fund_holdings` (`contract/src/fundholdings/`, includes pure `fundOverlap` for the browser), routes `/api/fund-holdings` and `/api/fund-holdings/:id` in `api/src/fundholdings/`; checks in its tests (C-076-1).
- Merged main into the branch; the planner-label gate no longer exists in CI, so PR #69's red job is gone.

## Next
- [ ] Confirm `gate` is green on PR #69 and it merges.
- [ ] Find a source each of the 10 houses serves to Actions (`config/fund_house_sources.json` has 5 of 10 unfound); until then they report 'cannot be fetched' in the run's lines.
- [ ] Weekly fund forecast and call (held, buy, watch) from NAV history, with track record; extend the existing fund call code rather than duplicating it; shapes in `contract/`.
- [ ] Report which fund detail the data can and cannot support (free additions).
- [ ] Unit checks: overlap from fixtures, returns/rolling/falls/cost/size from fixtures.

## Decisions
- Kept both sides when main's `feedback` dataset and our `funds` dataset collided in `contract/src/datasets.ts`.
- `fund_holdings` runs nightly: the schedule can only say trading days or every day; the Job is cheap and republishes the same month.
- `fund_holdings` is private visibility because the registry rule (C-203-1) makes anything named like holdings private.
- Overlap is computed in the browser; the route serves public fund portfolios only.
- Shapes live in `contract/`; no `web/` edits.

## Blocked
- Nothing yet.
