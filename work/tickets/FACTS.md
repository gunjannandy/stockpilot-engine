# FACTS: Stock facts in plain words against the sector, from XBRL filings first, with similar companies

## Ticket

Key `FACTS`, wave 2, machine **work**. Private parent: gunjannandy/stockpilot#153. Follow `work/README.md`.

Blocked by: STOCK, CHECKS2

## What to build

The father understands a company without jargon. The facts Job rides here: fundamentals from NSE XBRL filings first (v2 stores the filings index but never parsed the XBRL: build that parser), yfinance as fallback, promoter holding and pledge, every value a dated record with no look-ahead and with source, fetch time and "as of". On the stock page: price for ₹1 of yearly profit, return on equity, debt, profit growth, swings, biggest fall, trading, each with one plain sentence from fixed rules (port `plain.py`, matching known-good; no model writes these) and the sector's figure beside it; similar companies.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/sources/facts.py`
- `py/stockpilot/sources/facts_sources.py`
- `py/stockpilot/sources/fundamentals.py`
- `py/stockpilot/sources/filings.py`
- `py/stockpilot/jobs/ownership.py`
- `py/stockpilot/site_export/plain.py`
- `py/stockpilot/site_export/stock.py`
- `legacy/workflows/stock-facts.yml`

Stories: 40, 41, 126, 140 (numbers from the spec).

## Acceptance criteria

- [ ] `C-040-1` (preview e2e): facts block shows the fixture's exact values with sector comparisons
- [ ] `C-041-1` (preview e2e): similar companies listed
- [ ] `C-126-1` (unit): XBRL parse and fallback from fixtures
- [ ] `C-140-6` (unit): plain sentences per metric: the existing Python suite for this passes in py/ CI (no port)

## Owned paths

- `web/src/screens/stock/facts/**`
- `web/src/words/facts.*`
- `py/stockpilot/jobs/facts/**`
- `py/stockpilot/domain/plain/**`
- `py/stockpilot/domain/facts/**`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/v2/shots/stock-sk2-*`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/FACTS` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/FACTS` (and `preview/FACTS` to show it). The PR title starts with `FACTS:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
