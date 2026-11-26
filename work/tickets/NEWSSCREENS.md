# NEWSSCREENS: Market & news screen, the stock's news, Today's In the news, and news exposure per holding

## Ticket

Key `NEWSSCREENS`, wave 3, machine **work**. Private parent: gunjannandy/stockpilot#172. Follow `work/README.md`.

Blocked by: NEWSIMPACT, TODAY, PORTFOLIO, CHECKS3

## What to build

Every news surface reads the NEWSIMPACT table only. Market & news: live ranked cards with link-preview images and the stocks each affects, sector mood, coming up (results calendar), money from big funds (FII and DII flows, bulk and block deals; those Jobs ride here), and an "In today's news" list. The stock page lists its news with relation and direction. Today's "In the news" block. News exposure per Holding (direction × size × position) computed by code in the Worker.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `legacy/web/public/screens/news-live.js`
- `py/stockpilot/news_lists.py`
- `py/stockpilot/site_export/market.py`
- `py/stockpilot/sources/flows.py`
- `py/stockpilot/sources/events.py`
- `py/stockpilot/sources/deals.py`
- `py/stockpilot/sources/delivery.py`

Stories: 43, 66, 78, 84, 85 (numbers from the spec).

## Acceptance criteria

- [ ] `C-043-1` (preview e2e): news list shows relation and direction from the impact table
- [ ] `C-066-1` (unit): exposure arithmetic from fixtures
- [ ] `C-078-2` (screenshot): Market & news beside the prototype
- [ ] `C-084-1` (preview e2e): the three blocks show the fixture's exact values
- [ ] `C-085-1` (preview e2e): list renders from the impact table

## Owned paths

- `web/src/screens/market/**`
- `web/src/screens/stock/news/**`
- `web/src/screens/today/news/**`
- `web/src/words/market.*`
- `py/stockpilot/domain/exposure/**`
- `py/stockpilot/jobs/market-tide/**`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/v2/shots/market-*`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/NEWSSCREENS` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/NEWSSCREENS` (and `preview/NEWSSCREENS` to show it). The PR title starts with `NEWSSCREENS:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
