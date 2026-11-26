# TAXRSU: Portfolio's money tabs: tax and harvest, ITR download, RSUs, XIRR, risk, Nifty -10%, dividends calendar

## Ticket

Key `TAXRSU`, wave 2, machine **work**. Private parent: gunjannandy/stockpilot#157. Follow `work/README.md`.

Blocked by: PORTFOLIO, CHECKS2

## What to build

The money half of Portfolio, from PYDOMAIN and the existing Python: tax (gains booked, tax-free room, harvest ideas) and the ITR pack download; RSUs with value, tax and expected vests (the US price and USD/INR Jobs ride here); XIRR per Holding and for the portfolio against the Nifty; concentration by stock and sector; "what if the Nifty falls 10%"; a dividends and corporate-actions calendar with expected cash. Every number arrives precomputed by the nightly private Job ("as of last night"). Money numbers wait for the owner's Approve.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/book/rsu_view.py`
- `py/stockpilot/sources/usprices.py`
- `py/stockpilot/sources/fx.py`
- `legacy/web/public/app.js (tax tab)`

Stories: 59, 65 (numbers from the spec).

## Acceptance criteria

- [ ] `C-059-2` (preview e2e): download button returns the pack
- [ ] `C-065-1` (unit): calendar and cash from fixtures
- [ ] `C-065-2` (preview e2e): calendar shows the fixture's exact values

## Owned paths

- `web/src/screens/portfolio-money/**`
- `web/src/words/portfolio-money.*`
- `py/stockpilot/jobs/usprices/**`
- `py/stockpilot/domain/calendar_cash/**`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/ui/r10/`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/TAXRSU` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/TAXRSU` (and `preview/TAXRSU` to show it). The PR title starts with `TAXRSU:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
