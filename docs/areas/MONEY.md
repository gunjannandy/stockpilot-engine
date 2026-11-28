# Area MONEY

Status: building

## Done
- `money/src/index.ts` exports every money module as a namespace (#217).
- `api/src/portfolio/routes.ts`: signed-in `GET /api/portfolio/{holdings,trades,corporate-actions}` (raw rows, newest snapshot per source; the browser computes). Owner-only `GET /api/portfolio/settings`, `PUT /api/portfolio/{budget,mix}` (403 for anyone else).
- `api/drizzle/portfolio.ts` + `api/src/portfolio/migrations/`: `money_budgets`, `money_mix`.
- `contract/src/portfolio/portfolio.ts`: shapes for all of the above.
- `tools/migrate/settings.ts`: v2 budgets and target mix map.
- `api/src/money/routes.ts`: signed-in `GET /api/money/tax?fy=` (gains booked, net by pool, tax, tax-free room left); shape in `contract/src/money/money.ts`.
- `GET /api/money/xirr`: portfolio and per-stock XIRR from INR stock trades and newest `stock_history` close; Nifty read from symbol `NIFTY 50` there (null until that history exists); shape `XirrResponse`.
- Tests: `api/src/portfolio/routes.test.ts`, `api/src/money/routes.test.ts`.

## Next
- [ ] Register `money_budgets` / `money_mix` as private datasets if the migrate sink needs them (check `contract/src/datasets.ts` rules).
- [ ] `api/src/money/`: harvest ideas on the tax route (needs latest prices), RSU view route and risk route over `loadRebuild` (`money/src/{rsu,risk}`); shapes in `contract/`.
- [ ] US price and USD/INR Job: `py/stockpilot/jobs/usprices/`, `.github/workflows/usprices.yml`; reuse `api/src/fx/rates.ts`; register dataset, write budget, heartbeat.
- [ ] Dividends and corporate-actions calendar data with expected cash.
- [ ] Fidelity fixtures (#250) and deleting the ported Python (#218, #233): only after the private real-data check matches; both held.
- [ ] Opus review chapter over the whole diff for money correctness.

## Decisions
- Budget and mix are tables of rows (month / asset class), not a JSON blob, so v2's rows migrate one for one; a write replaces the whole setting in one batch.
- Holdings route returns only the newest snapshot of each source, so a new Kite sync shows with no Job.
- `money` exports are namespaces, because `Row`, `RateOn`, `Holding` collide across modules.
- Owner-only uses the existing `ownerOnly` guard from auth (read and write alike).

- XIRR skips dollar trades (RSU view will value those) and returns null, with a warning, when a held stock has no price.
- CI `ts` failure on #78 (C-129-1 could not resolve a scaffold package) did not reproduce after merging main: full `pnpm test` green locally; treated as a flake from another area's scaffold check.

## Blocked
- Private real-data match (needed to delete the ported Python and capture Fidelity fixtures) needs the owner's vault rows, which exist nowhere a cloud builder can reach.

Chapter end: 2
