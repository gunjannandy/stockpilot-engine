# Area STOCK: stock universe, history, chart files, search, quotes, facts

Status: building

## Done
- Stock routes, load-on-demand: `api/src/stocks/` (migration, routes, test); checks `checks/C-045-1.test.ts`.
- Quotes cache and market-hours duty: `api/src/quotes/`; check `checks/C-046-1.test.ts`.
- Contract shapes: `contract/src/stocks/stocks.ts`; datasets `history` and `universe` in `contract/src/datasets.ts`.
- Jobs `py/stockpilot/jobs/history/`, `py/stockpilot/jobs/universe/`; workflows `.github/workflows/history.yml`, `universe.yml`.
- PR #67 gate fixed: merged main (dataset conflict kept both sides); the planner-label gate no longer exists on main.

- Facts Job: `py/stockpilot/jobs/facts/` (templates English and Bengali, raw figures, sector comparison), `api/src/facts/` (route /api/facts/:symbol, migration), `contract/src/facts/facts.ts`, dataset `facts`, `.github/workflows/facts.yml`; checks `checks/C-048-1.py`, `checks/C-171-2.py`.

## Next
- [x] Check C-047-1 (`checks/C-047-1.py`): universe keeps delisted and renamed stocks (old name kept as alias).
- [x] Check C-040-4 (`checks/C-040-4.py`): `backfill_all` in the history Job (subject `backfill`), unexplained jumps held back, 2% threshold.
- [x] Chart file: `GET /api/stocks/:symbol/chart` (`api/src/stocks/chart.ts`, shape `ChartResponse`): split-adjusted prices, 2- and 10-month averages. Search index is the universe dataset behind `/api/stocks/search`.
- [x] Facts Job and checks C-048-1, C-171-2.
- [ ] Quotes duty in `api/src/schedule/duties.ts` (shared file; quotes stay empty until wired) and typed web client entries in `tools/contract-gen/gen.ts`.
- [ ] Facts: feed `price_sentences` (biggest fall, swings, trading) from history rows in the Job (written and tested, not yet fed); similar companies list.
- [ ] Production check C-040-3 (last close vs bhavcopy for 5 samples) once data runs.
- [ ] Set Status: done when all green.

## Decisions
- Added `history.yml` and `universe.yml` to the allowed list in `checks/MOVE-2.py`, as calendar and archive did before; the planner-label gate that guarded this was dropped on main.
- `checks/C-145-1.py::test_ping_path_runs_on_node_and_sqlite` timed out locally (API start >10s in the sandbox); not this area, left alone.

- Facts rows use flat columns plus JSON text for sentences and figures (a row's fields are table columns), like funds; no drizzle file needed (dataset_rows holds the rows).
- Added `facts.yml` to the allowed list in `checks/MOVE-2.py` and `facts` to the job kinds in `contract/src/core/jobs.ts` (shared files, one line each).

- Chart files are built by the Worker from stored days on request, not as static files, so they need no extra Job output or release.

## Blocked
- none

Chapter end: 2
