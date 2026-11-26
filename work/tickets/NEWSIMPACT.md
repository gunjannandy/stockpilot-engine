# NEWSIMPACT: News every 15 minutes judged once per stock into one append-only impact table

## Ticket

Key `NEWSIMPACT`, wave 3, machine **work**. Private parent: gunjannandy/stockpilot#171. Follow `work/README.md`.

Blocked by: MODELS, STOCK, CHECKS3

## What to build

Fix the Airtel mistake for good. The bug is in v2's `news_rank.spread()`: `news_tag` already asks the model for each touched stock's relation, direction and size, and `spread()` throws that away and fans a sector tag out to every held stock in the sector. In v3: a public Job collects news every 15 minutes (port `news_collect`: grouping one event's reports, source counts, name-to-ticker matching; filings rank above wire and wire above blogs) with its heartbeat. The model judges each affected stock once, reading the article for high-impact items and never seeing holdings, and writes one append-only row per item and stock: relation (self, rival, supplier, customer), direction, size, why, model, time. A stock that only shares the sector gets a grey "sector news" mark, never a direction. Everything that can move a forecast reads only this table: refresh triggers, forecast levels and bands, change marks, In today's news, near-live price picks, exposure, the nightly note; a contract test fails if any consumer reads the raw sector tag. Link-preview images come from the `og` route (ported) that returns an image or a placeholder.

In Python: keep `news_collect` and `news_tag`; delete `news_rank.spread()`; write one impact row per item and stock through the ingest door.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/sources/news_collect.py`
- `py/stockpilot/news_tag.py`
- `py/stockpilot/news_rank.py (read to see the bug; do not port spread)`
- `legacy/web/functions/api/v2/news.js`
- `legacy/web/functions/api/v2/og.js`
- `py/tests/news_collect/`
- `py/tests/news_tier/`

Stories: 82 (numbers from the spec).

## Acceptance criteria

- [ ] `C-082-1` (unit): source weights order fixtures

## Owned paths

- `py/stockpilot/jobs/news/**`
- `py/stockpilot/domain/news/**`
- `contract/src/news.ts`

## Owner's Approve

This ticket changes money, tax, numbers or forecast rules: do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/NEWSIMPACT`. The PR title starts with `NEWSIMPACT:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
