# FUNDS: Funds: every fund searchable, fund page with NAV chart and our buys, returns against category and Nifty, falls, cost, size

## Ticket

Key `FUNDS`, wave 2, machine **work**. Private parent: gunjannandy/stockpilot#159. Follow `work/README.md`.

Blocked by: STOCK, CHECKS2

## What to build

The fund data Jobs ride with this screen: AMFI's scheme master grouped into funds with plan and option variants, NAV history (windows of at most 90 days), TER and AUM, fund stats (1, 3 and 5-year returns, the Category middle) and research ranks inside each fund group, matching known-good. Every fund is searchable; a fund page shows its NAV chart with our buys, returns against the category and the Nifty, rolling returns, falls, cost and size. Overlap is FUNDOVERLAP's; the Fund call and fund Analyse arrive in MODELNOTES.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/sources/fund_universe.py`
- `py/stockpilot/sources/navhistory.py`
- `py/stockpilot/sources/funds.py`
- `py/stockpilot/sources/fundcosts.py`
- `py/stockpilot/sources/fund_stats.py`
- `py/stockpilot/fundresearch.py`
- `py/stockpilot/fundgroups.py`
- `py/stockpilot/analysis/fundreview.py`
- `legacy/web/public/screens/funds.js`
- `legacy/web/public/screens/funds-core.js`

Stories: 74, 75, 140 (numbers from the spec).

## Acceptance criteria

- [ ] `C-074-1` (preview e2e): fund page shows the fixture's exact values
- [ ] `C-074-2` (screenshot): Funds beside the prototype
- [ ] `C-075-1` (unit): fund stats from fixtures
- [ ] `C-140-5` (unit): fund stats and fund research ranks: the existing Python suite for this passes in py/ CI (no port)

## Owned paths

- `web/src/screens/funds/**`
- `web/src/words/funds.*`
- `py/stockpilot/jobs/funds/**`
- `py/stockpilot/domain/funds/**`
- `contract/src/funds.ts`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/ui/r10/`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/FUNDS` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/FUNDS` (and `preview/FUNDS` to show it). The PR title starts with `FUNDS:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
