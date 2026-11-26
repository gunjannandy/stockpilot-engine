# MARKS: Change marks and 'why is this here' chips on every screen

## Ticket

Key `MARKS`, wave 2, machine **work**. Private parent: gunjannandy/stockpilot#164. Follow `work/README.md`.

Blocked by: TODAY, LISTS, PORTFOLIO, FUNDS, RECORD, CHECKS2

## What to build

One ticket builds the marks for every screen. Yellow change marks on rows, rail tabs and the browser tab; a What changed strip and Mark all seen. In v3 the Change feed is shared: a row clears when either person opens it (v2 kept it per person; update the GLOSSARY entry). A "why is this here" chip on every list row, so every row carries at least one reason.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `legacy/web/public/screens/changes.js`
- `legacy/web/functions/api/v2/changes/`
- `legacy/web/lib/v2/handlers.js (changes)`

Stories: 18, 19 (numbers from the spec).

## Acceptance criteria

- [ ] `C-018-2` (preview e2e): marks, strip and Mark all seen work
- [ ] `C-019-1` (preview e2e): every row carries at least one reason chip

## Owned paths

- `web/src/marks/**`
- `contract/src/marks.ts`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/v2/shots/today-*`, `docs/prototypes/v2/shots/watchlist-*`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/MARKS` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/MARKS` (and `preview/MARKS` to show it). The PR title starts with `MARKS:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
