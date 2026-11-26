# STOCK: Stock page and price data: history, chart with Open in, load on demand, near-live price

## Ticket

Key `STOCK`, wave 2, machine **work**. Private parent: gunjannandy/stockpilot#152. Follow `work/README.md`.

Blocked by: SHELL, JOBSCORE, CHECKS2

## What to build

Open any listed company and see the story of its price. The data Jobs ride with this screen:
- daily price history: keep the existing Parquet files on the engine's releases and their format (no re-backfill unless the format must change); port the daily append and the chart files, delisted and renamed stocks kept (survivorship-free), read by DuckDB in Jobs; the price-jump hard check (a move over 40% that no corporate action explains) registers with INSTANT's last-good mechanism;
- near-live prices in market hours: v2's quotes Worker ported to a Hono route on a timer, served from the edge cache within an age limit, the age always shown;
- a stock never loaded starts one load Job and shows its progress.

The page: a Lightweight Charts chart of 6 months, 1 year or all, with 2- and 10-month averages, levels, forecast bands and our buys; one "Open in" menu in each chart's corner (Kite chart, Screener.in), never on list rows. The page frame leaves slots that FACTS, CALLS, PORTFOLIO and NEWSSCREENS fill behind flags.

The Universe Job that builds the search index (every NSE, NSE SME, BSE and BSE SME stock, delisted kept, and every fund) rides here, from `universe.py` and `search_index.py`, with its heartbeat.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/sources/history.py`
- `py/stockpilot/sources/chart_files.py`
- `py/stockpilot/sources/marketdata.py`
- `py/stockpilot/verify/flags.py`
- `legacy/web/quotes/worker.js`
- `legacy/web/lib/v2/quotes.js`
- `legacy/web/public/screens/stock.js`
- `legacy/workflows/history-daily.yml`
- `legacy/workflows/chart-files.yml`
- `py/stockpilot/sources/universe.py`
- `py/stockpilot/sources/search_index.py`

Stories: 38, 39, 125 (numbers from the spec).

## Acceptance criteria

- [ ] `C-038-1` (preview e2e): chart ranges, averages, bands and buys render
- [ ] `C-038-2` (screenshot): stock page beside the prototype
- [ ] `C-039-1` (preview e2e): one menu per chart; none on rows; links point to the right instrument
- [ ] `C-125-1` (unit): universe keeps delisted and renamed fixtures

## Owned paths

- `web/src/screens/stock/page/**`
- `web/src/screens/stock/chart/**`
- `web/src/words/stock.*`
- `web/src/charts/**`
- `py/stockpilot/jobs/history/**`
- `contract/src/stocks.ts`
- `py/stockpilot/jobs/universe/**`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/v2/shots/stock-sk2-*`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/STOCK` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/STOCK` (and `preview/STOCK` to show it). The PR title starts with `STOCK:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
