# FUNDS

Status: building

## Done
- Funds Job: `py/stockpilot/jobs/funds/__init__.py`, workflow `.github/workflows/funds.yml` (allowed in `checks/MOVE-2.py`).
- Dataset `funds` (schemes with stats and NAVs): `contract/src/funds/funds.ts`, registered in `contract/src/datasets.ts`.
- API: `api/src/funds/routes.ts`, migration `api/src/funds/migrations/`, tests `api/src/funds/funds.test.ts`.
- Merged main into the branch; the planner-label gate no longer exists in CI, so PR #69's red job is gone.

## Next
- [ ] Confirm `gate` is green on PR #69 and it merges.
- [ ] Fund search route over the whole universe (name, house, category).
- [ ] Fund-holdings Job for the 10 largest houses, with a source each serves to Actions; record houses that cannot be fetched; overlap route against our stocks; shapes in `contract/`.
- [ ] Weekly fund forecast and call (held, buy, watch) from NAV history, with track record; extend the existing fund call code rather than duplicating it; shapes in `contract/`.
- [ ] Report which fund detail the data can and cannot support (free additions).
- [ ] Unit checks: overlap from fixtures, returns/rolling/falls/cost/size from fixtures.

## Decisions
- Kept both sides when main's `feedback` dataset and our `funds` dataset collided in `contract/src/datasets.ts`.
- Shapes live in `contract/`; no `web/` edits.

## Blocked
- Nothing yet.
