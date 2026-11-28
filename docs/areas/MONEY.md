# Area MONEY

Status: done

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
- `GET /api/money/calendar` (dated actions of held stocks from `calendar`; expected dividend cash = last year's ex-dates +1y × shares held; `CalendarResponse`); dividends Job `py/stockpilot/jobs/dividends/`, `.github/workflows/dividends.yml`, dataset `dividends` (06:45 IST), ingest `POST /api/money/dividends`, `GET /api/money/held-symbols`, table `dividends`.
- Tests: `api/src/portfolio/routes.test.ts`, `api/src/money/routes.test.ts`.

## Next
- [ ] Opus review chapter over the whole diff for money correctness.

## Decisions
- Chapter 6: merged main (news area added `news` Job kind, dataset and workflow allow-list entry); kept both sides in `contract/src/core/jobs.ts`, `contract/src/datasets.ts`, `checks/MOVE-2.py`. Full `pnpm test` green. No stored beta or US corporate-action source exists yet, so nothing new could be built.
- Budget and mix are tables of rows (month / asset class), not a JSON blob, so v2's rows migrate one for one; a write replaces the whole setting in one batch.
- Holdings route returns only the newest snapshot of each source, so a new Kite sync shows with no Job.
- `money` exports are namespaces, because `Row`, `RateOn`, `Holding` collide across modules.
- Owner-only uses the existing `ownerOnly` guard from auth (read and write alike).

- XIRR skips dollar trades (RSU view will value those) and returns null, with a warning, when a held stock has no price.
- CI `ts` failure on #78 (C-129-1 could not resolve a scaffold package) did not reproduce after merging main: full `pnpm test` green locally; treated as a flake from another area's scaffold check.
- Risk route uses sector "Unknown" and beta 1 because neither is stored anywhere yet; the response lists the assumed-beta symbols.
- RSU tax: top slab on short-term gain, long-term after 730 days at the other-assets rate (unlisted foreign shares); US closes live in own table `us_prices`, since `stock_history` only allows NSE/BSE (stocks area's file untouched).
- Added `usprices.yml` to the allow-list in `checks/MOVE-2.py` (shared file, one word) and `usprices` to `JobKind` in contract core.
- Dividends and `calendar` rows are expected cash only as an estimate (repeat last year); `dividends.yml` also added to the MOVE-2 allow-list.
- `money_budgets` / `money_mix` are not datasets (written by owner routes, no Job), so no registry entry.
- Risk sector now read from the newest `facts` row per symbol (stocks area's table, read only; missing table or row means Unknown).
- Merge of main: main held a squash of an earlier part of this branch, so conflicting money files took this branch's side (a superset).
- Tax/ITR Python (#233) stays: C-069-2 does not cover it and no private check exists.

- #218 not deleted in chapter 6: the ported lots and positions Python still has live importers outside this area, and removing them would break CI.
- Chapter 7: #250 is met by C-069-2 (real rows went through the compared rebuild); real-row fixtures never go in the public engine, so none are added.
- Left out: stored beta (no free source; risk keeps beta 1 and lists the assumed symbols) and US corporate-action split terms for expected RSU vests (no free source).
- Left out: deleting `trades/lots.py` and `book/{positions,units,record,acted}.py` (#218). About 25 live importers sit in other areas (forecast, verify, asks, fundcall, dossier, analysis, jobs/docs, trades parsers) and their tests; removing the modules would break CI or mean rewriting those areas. They go with their last importer when that area ports. Not an owner blocker.
- Tax/ITR Python (#233) stays; its private check and deletion are #297, outside this area.

## Blocked

Chapter end: 7
