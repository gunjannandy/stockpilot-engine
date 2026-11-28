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
- Tax route returns `harvest` (newest stored closes, today's date); `GET /api/money/risk` (concentration + Nifty -10%), `RiskResponse` in contract.
- `GET /api/money/rsu` (dollar lots valued at newest `us_prices` close and `fx_rates`, tax if sold, expected vests; `RsuResponse`), ingest `POST /api/money/us-prices`, `GET /api/money/us-symbols`, `POST /api/money/fx-refresh`; migration `api/src/money/migrations/`.
- usprices Job: `py/stockpilot/jobs/usprices/`, `.github/workflows/usprices.yml`, dataset `usprices` (06:30 IST daily, budget 300), test `py/tests/usprices/`.
- Tests: `api/src/portfolio/routes.test.ts`, `api/src/money/routes.test.ts`.

## Next
- [ ] Register `money_budgets` / `money_mix` as private datasets if the migrate sink needs them (check `contract/src/datasets.ts` rules).
- [ ] Store sector and beta (stocks area) so risk stops reading "Unknown" and beta 1.
- [ ] RSU: splits for expected vests (corporate-action terms of US symbols); payslip vests.
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
- Risk route uses sector "Unknown" and beta 1 because neither is stored anywhere yet; the response lists the assumed-beta symbols.
- RSU tax: top slab on short-term gain, long-term after 730 days at the other-assets rate (unlisted foreign shares); US closes live in own table `us_prices`, since `stock_history` only allows NSE/BSE (stocks area's file untouched).
- Added `usprices.yml` to the allow-list in `checks/MOVE-2.py` (shared file, one word) and `usprices` to `JobKind` in contract core.
- Tax/ITR Python (#233) stays: C-069-2 does not cover it and no private check exists.

## Blocked
- Private real-data match (needed to delete the ported Python and capture Fidelity fixtures) needs the owner's vault rows, which exist nowhere a cloud builder can reach.

Chapter end: 3
