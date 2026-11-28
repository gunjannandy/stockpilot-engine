# Area STOCK: stock universe, history, chart files, search, quotes, facts

Status: building

## Done
- Stock routes, load-on-demand: `api/src/stocks/` (migration, routes, test); checks `checks/C-045-1.test.ts`.
- Quotes cache and market-hours duty: `api/src/quotes/`; check `checks/C-046-1.test.ts`.
- Contract shapes: `contract/src/stocks/stocks.ts`; datasets `history` and `universe` in `contract/src/datasets.ts`.
- Jobs `py/stockpilot/jobs/history/`, `py/stockpilot/jobs/universe/`; workflows `.github/workflows/history.yml`, `universe.yml`.
- PR #67 gate fixed: merged main (dataset conflict kept both sides); the planner-label gate no longer exists on main.

## Next
- [x] Check C-047-1 (`checks/C-047-1.py`): universe keeps delisted and renamed stocks (old name kept as alias).
- [ ] Check C-040-4: backfill gives each listed fixture stock full history; unexplained jump held back with reason; run passes under threshold.
- [ ] Chart files and search index output in the universe/history Jobs.
- [ ] Facts Job (XBRL first, yfinance fallback, sector comparison, plain sentences in English and Bengali, raw figures table with value, period, source): `py/stockpilot/jobs/facts/`, `api/src/facts/`, `api/drizzle/facts.ts`, `.github/workflows/facts.yml`, contract shapes. Checks C-048-1, C-171-2.
- [ ] Production check C-040-3 (last close vs bhavcopy for 5 samples) once data runs.
- [ ] Set Status: done when all green.

## Decisions
- Added `history.yml` and `universe.yml` to the allowed list in `checks/MOVE-2.py`, as calendar and archive did before; the planner-label gate that guarded this was dropped on main.
- `checks/C-145-1.py::test_ping_path_runs_on_node_and_sqlite` timed out locally (API start >10s in the sandbox); not this area, left alone.

## Blocked
- none
