# LISTS: Worth following (List and Table screener) and Watchlist with star, Not now and Undo

## Ticket

Key `LISTS`, wave 2, machine **work**. Private parent: gunjannandy/stockpilot#155. Follow `work/README.md`.

Blocked by: CALLS, CHECKS2

## What to build

Worth following is one rail item with a List / Table switch that survives a reload. List: Top 10, Just missed (Near misses), has our view, you hold, falling for months, busy today. Table: the screener over the whole Universe with filter chips and a verdict filter (v2's All calls tab and Screener fold in here; the universe-table Job rides with it). Watchlist: star toggles, inline add, our view per row, Undo; a star writes one row straight through the API with no Job (removal is soft, so undo is an add). Not now for a week or a month, with Undo; not-now rows expire by themselves. Snooze, dismiss, learned-forget and the Ideas tab are not ported.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `legacy/web/public/screens/worth.js`
- `legacy/web/public/screens/universe.js`
- `legacy/web/public/screens/universe-core.js`
- `py/stockpilot/sources/screen_table.py`
- `py/stockpilot/list_writers.py`
- `py/stockpilot/watchlist.py`
- `py/stockpilot/book/not_now.py`
- `py/stockpilot/analysis/opportunities.py`
- `legacy/web/functions/api/v2/lists/[name].js`

Stories: 47, 48, 49, 50, 52 (numbers from the spec).

## Acceptance criteria

- [ ] `C-047-1` (preview e2e): list sections render from the screen
- [ ] `C-047-2` (screenshot): Worth following beside the prototype
- [ ] `C-048-1` (preview e2e): table filters by chip and verdict over the full universe
- [ ] `C-049-1` (preview e2e): switch toggles views and survives a reload
- [ ] `C-050-1` (preview e2e): star, add and Undo work
- [ ] `C-050-2` (screenshot): Watchlist beside the prototype
- [ ] `C-052-2` (preview e2e): Not now and Undo on a row

## Owned paths

- `web/src/screens/follow/**`
- `web/src/screens/watchlist/**`
- `web/src/words/follow.*`
- `web/src/words/watchlist.*`
- `py/stockpilot/jobs/universe-table/**`
- `contract/src/lists.ts`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/v2/shots/follow-*`, `docs/prototypes/v2/shots/watchlist-*`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/LISTS` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/LISTS` (and `preview/LISTS` to show it). The PR title starts with `LISTS:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
