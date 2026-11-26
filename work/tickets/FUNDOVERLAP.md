# FUNDOVERLAP: Fund overlap with our stocks, from the 10 largest fund houses' monthly portfolios

## Ticket

Key `FUNDOVERLAP`, wave 2, machine **work**. Private parent: gunjannandy/stockpilot#160. Follow `work/README.md`.

Blocked by: FUNDS, CHECKS2

## What to build

The father avoids doubling up. Port the parsers for the 10 largest fund houses' monthly portfolio files (SEBI makes each publish one) into dated ISIN rows in a public Job with its heartbeat. The overlap with the stocks we hold is computed behind sign-in (holdings never reach a public Job) and shown on the fund page.

v2's `fund-holdings` Job fails with HTTP 403 today: find a source each fund house serves to Actions, or record which ones cannot be fetched.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/sources/fund_holdings.py`
- `config/fund_house_sources.json`
- `py/tests/fund_holdings/`

Stories: 76 (numbers from the spec).

## Acceptance criteria

- [ ] `C-076-1` (unit): overlap from fixtures

## Owned paths

- `py/stockpilot/jobs/fund-holdings/**`
- `py/stockpilot/domain/overlap/**`
- `web/src/fund-overlap/**`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/ui/r10/`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/FUNDOVERLAP` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/FUNDOVERLAP` (and `preview/FUNDOVERLAP` to show it). The PR title starts with `FUNDOVERLAP:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
