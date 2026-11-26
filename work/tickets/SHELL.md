# SHELL: Shell: rail from the inventory, search with /, English and Bengali, themes, text size, keys, one scroll

## Ticket

Key `SHELL`, wave 1, machine **work**. Private parent: gunjannandy/stockpilot#146. Follow `work/README.md`.

Blocked by: SKELETON, CHECKS1

## What to build

The frame every screen lives in, matching the r10 structure and the DESIGN.md look (shadcn/ui themed from its tokens; React, Vite, TanStack Router).
- The rail (Today, Worth following, Watchlist, Portfolio, Funds, Market & news, Record, Feedback, Admin) is generated from the inventory, so a screen is added by data. v2's `TABS` and `NAV` fold in: the hidden "calls" tab and the "universe" (Screener) item become Worth following's Table view; Ideas, Settings and Health go (Admin replaces the last two). Each item opens its screen; unbuilt screens sit behind feature flags.
- Search everything from anywhere, `/` to focus, forgiving spelling (Fuse.js). The Universe Job that builds the search index (every NSE, NSE SME, BSE and BSE SME stock, delisted kept, and every fund) is ported from `universe.py` and `search_index.py` and rides with this ticket, with its heartbeat.
- English and Kolkata Bengali, trade words kept in English letters; v2's word table is split into words files per screen (the shell's own words here; each screen ticket moves its own); the build fails on any fixed word without Bengali.
- Light and dark themes; a text-size switch that survives a reload; arrows move through lists and Esc goes back; one scroll where only the list scrolls and the pane stays.
- Desktop first (1440, 1100) and phone (400) with no sideways scroll.

Sign-in is mocked here (SIGNIN makes it real). Search reads the index file; the Universe Job that builds the index moves to STOCK (review F7).

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `legacy/web/public/app.js (TABS, NAV, the word table, about 349 keys)`
- `legacy/web/public/search.js`
- `legacy/web/public/locale-guard.js`
- `DESIGN.md`

Stories: 7, 8, 9, 10, 11, 12, 13, 14 (numbers from the spec).

## Acceptance criteria

- [ ] `C-007-1` (preview e2e): each rail item opens its screen
- [ ] `C-007-2` (screenshot): shell beside the r10 prototype at 1440, 1100 and 400 px
- [ ] `C-008-1` (preview e2e): / focuses search; a fuzzy name finds the stock
- [ ] `C-009-1` (unit): the build fails on any fixed word without Bengali
- [ ] `C-009-2` (preview e2e): the switch changes every fixed word
- [ ] `C-010-1` (screenshot): both themes on the baseline screens
- [ ] `C-011-1` (preview e2e): the switch scales text and survives a reload
- [ ] `C-012-1` (preview e2e): arrows move the selection; Esc returns
- [ ] `C-013-1` (preview e2e): the pane stays put while the list scrolls
- [ ] `C-014-1` (screenshot): every approved screen at 1440, 1100 and 400 px with no sideways scroll

## Owned paths

- `web/src/shell/**`
- `web/src/words/shell.*`
- `web/src/search/**`
- `tools/inventory/**`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/ui/r10/`, `docs/prototypes/v2/shots/today-*`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/SHELL` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/SHELL` (and `preview/SHELL` to show it). The PR title starts with `SHELL:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
