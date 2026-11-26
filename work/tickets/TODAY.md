# TODAY: Today: the day's call line, money left, market health, portfolio summary, groups, print on one A4

## Ticket

Key `TODAY`, wave 2, machine **work**. Private parent: gunjannandy/stockpilot#158. Follow `work/README.md`.

Blocked by: CALLS, PORTFOLIO, CHECKS2

## What to build

The father's first screen answers "what should we do today?" in one line built from the latest Calls; "Nothing to do today" is a valid answer. Money left to invest this month (Budget minus this month's buys). Market health (from PORTFORECAST): how many stocks are going up, the Nifty's direction, whether the market is cheap. A portfolio summary that matches Portfolio's totals. Stocks grouped as Sell, Weak, Fine keep, Close to a buy, Unusual today. Print Today on one A4 page. The "In the news" block slots in with NEWSSCREENS.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `legacy/web/public/app.js (today tab)`
- `py/stockpilot/site_export/calls.py`

Stories: 23, 24, 26, 27, 29 (numbers from the spec).

## Acceptance criteria

- [ ] `C-023-1` (preview e2e): Today's call line renders from the latest calls
- [ ] `C-023-2` (screenshot): Today beside the prototype
- [ ] `C-024-1` (preview e2e): budget minus this month's buys
- [ ] `C-026-1` (preview e2e): portfolio summary matches the Portfolio totals
- [ ] `C-027-1` (preview e2e): groups follow the call verdicts
- [ ] `C-029-1` (preview e2e): print layout fits one A4 page

## Owned paths

- `web/src/screens/today/**`
- `web/src/words/today.*`
- `contract/src/today.ts`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/v2/shots/today-*`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/TODAY` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/TODAY` (and `preview/TODAY` to show it). The PR title starts with `TODAY:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
