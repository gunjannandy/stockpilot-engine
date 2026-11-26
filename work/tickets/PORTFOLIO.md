# PORTFOLIO: Portfolio: All / Kite / Smallcase, holdings, target mix and budget, worth a look, our holding on the stock page

## Ticket

Key `PORTFOLIO`, wave 2, machine **work**. Private parent: gunjannandy/stockpilot#156. Follow `work/README.md`.

Blocked by: STOCK, PYDOMAIN, CHECKS2

## What to build

Everything we own on one screen, from PORTTAX and PORTLOTS. An All / Kite / Smallcase switch whose totals, tax and exposure follow the scope. Each Holding's value, gain, share, tax status, bought date, shares, cost and long-term-from date. What we own against the Target allocation ("target mix" on screen); the owner sets the monthly Budget and the Target allocation (owner-only rows). "Worth a look for the portfolio". Tax: gains booked, tax-free room, harvest ideas; download the ITR pack. RSUs with value, tax and expected vests (the US price and USD/INR Jobs ride here). XIRR per Holding and portfolio against the Nifty; concentration by stock and sector; "what if the Nifty falls 10%"; a dividends and corporate-actions calendar with expected cash. Also our Holding block on the stock page. "I hold this for years" is not ported. Money numbers wait for the owner's Approve.

Tax, the ITR download, RSUs, XIRR, risk, the Nifty −10% view and the dividends calendar are TAXRSU's (review F7).

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/views.py`
- `py/stockpilot/book/rsu_view.py`
- `py/stockpilot/book/budget.py`
- `py/stockpilot/weekly.py`
- `py/stockpilot/sources/usprices.py`
- `py/stockpilot/sources/fx.py`
- `legacy/web/functions/api/v2/budget.js`
- `legacy/web/public/screens/records.js`
- `legacy/web/public/app.js (portfolio and tax tabs)`

Stories: 44, 53, 54, 55, 57 (numbers from the spec).

## Acceptance criteria

- [ ] `C-044-1` (preview e2e): holding block matches Portfolio
- [ ] `C-053-1` (preview e2e): scope switch changes totals, tax and exposure
- [ ] `C-053-2` (screenshot): Portfolio beside the prototype
- [ ] `C-054-1` (preview e2e): holdings table columns show the fixture's exact values
- [ ] `C-055-1` (unit): mix gaps from fixtures
- [ ] `C-057-1` (preview e2e): suggestions block shows the fixture's exact values

## Owned paths

- `web/src/screens/portfolio/**`
- `web/src/screens/stock/holding/**`
- `web/src/words/portfolio.*`
- `py/stockpilot/jobs/usprices/**`
- `contract/src/portfolio.ts`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/ui/r10/`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/PORTFOLIO` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/PORTFOLIO` (and `preview/PORTFOLIO` to show it). The PR title starts with `PORTFOLIO:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
