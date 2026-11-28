# Area NEWS: news every 15 minutes, impact per stock, morning email

Status: building

## Done
- News Job `py/stockpilot/jobs/news/` (`weights.py` source weights, `impact.py` judge once per item and stock, `__init__.py` run); workflow `.github/workflows/news.yml`; duty `api/src/news/duty.ts` starts one Job per quarter hour (subject = IST slot).
- Contract `contract/src/news/news.ts`; dataset `news_items` in `contract/src/datasets.ts`; job kind `news`.
- Worker: `api/src/news/` (append-only impact door, `readImpact` reader seam, cards, stock's news, contract helper), `api/drizzle/news.ts`, migration.
- og route `api/src/og/routes.ts` (page image or placeholder, public hosts only).
- Morning email `api/src/email/` (owner and father HTML, health-unreachable line), prototype digest `api/src/digest/`.
- Email feeds: mood and coming up in `api/src/email/routes.ts` (C-108-3); `news_rank.spread` removed.
- Checks: C-078-1, C-079-1, C-080-1, C-081-1, C-082-1, C-083-1, C-108-1, C-110-1, C-165-1.

## Next
- [ ] Register each consumer's files in `CONSUMER_FILES` (api/src/news/contract.ts) as their areas land (refresh triggers, forecast, change marks, near-live picks, exposure, nightly note).
- [ ] Email: call line from `money/src/callline/` (not on main yet), changes, build progress and soak counter feeds (no source exists yet); Apps Script fetch (C-108-2, C-109-1 are production checks).
- [ ] Move In-the-news list rules from `py/stockpilot/news_lists.py` onto `readImpact` when the UI area lands its pane.
- [ ] Model access for the judge in the Job (see Blocked); until then items are ranked and published but not judged.
- [ ] Archive of news older than 90 days (the Job already beats `job.news`; the duty beats through the shared duty runner).
- [ ] Set Status: done when all green.

## Decisions
- Impact table is insert-only by construction (no update or delete path, scan in C-079-1) because the migration runner splits on `;` and bars `delete`, so triggers cannot ship.
- Impact has its own signed door `/api/news/impact` (not the publish door) since the publish door replaces a dataset per run and the table must accumulate.
- `news_judged` remembers items the model answered for, so an item with no stock is not judged again.
- Added `news` to the duty list in `api/src/schedule/duties.ts`, `JobKind` in `contract/src/core/jobs.ts`, `news.yml` in `checks/MOVE-2.py` and the `news` duty in `checks/C-116-3.test.ts` (shared files, one line each).
- Source weights: filings (NSE, BSE, SEBI, RBI) 3, wires and known publishers 2, anything else 1.
- Legacy `news_rank.spread` left for now: existing `news_tier` tests still call it.

- `news_rank.spread()` deleted; its reach logic stays as the private `_reach` inside `rank()` (closeness only, never a direction) so the existing `news_tier` rank tests stay green; the spread test now checks reach through `rank`.
- Email mood comes from impact directions only (sector-only rows ignored); coming up is the next 7 days of the `calendar` dataset.

## Blocked
- Model token for the news Job (judging needs a model; `_job.yml` carries none). Name: a model API secret passed to `news.yml`.
- private run: C-108-2 morning email sent each trading day
- private run: C-109-1 the father's version is sent

Chapter end: 2
