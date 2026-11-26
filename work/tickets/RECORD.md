# RECORD: Record: our forecasts against the Nifty, are we adding value, our own trading, Smallcase against our trades

## Ticket

Key `RECORD`, wave 2, machine **work**. Private parent: gunjannandy/stockpilot#161. Follow `work/README.md`.

Blocked by: CALLS, CHECKS2

## What to build

The nightly scoring Job (with its heartbeat) scores every Call at 1, 3 and 6 months using PORTCALLS. The Record screen shows the Track record against the Nifty (Unproven until enough Calls are scored); "are we adding value": our Calls against holding the Nifty and an equal-weight Watchlist; our own trading (trades closed, made money, winners and losers held, sold too early, gains booked each month); Smallcase against our own trades. Post-mortems on missed Calls arrive in MODELNOTES.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `legacy/web/public/screens/records.js`
- `py/stockpilot/book/smallcase.py`
- `py/stockpilot/book/pairs.py`
- `py/stockpilot/ops.py (scoring step)`

Stories: 86, 87, 90 (numbers from the spec).

## Acceptance criteria

- [ ] `C-086-2` (screenshot): Record beside the prototype
- [ ] `C-087-1` (unit): benchmarks from fixtures
- [ ] `C-090-1` (unit): comparison from fixtures

## Owned paths

- `web/src/screens/record/**`
- `web/src/words/record.*`
- `py/stockpilot/jobs/scoring/**`
- `contract/src/record.ts`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/ui/r10/`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/RECORD` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/RECORD` (and `preview/RECORD` to show it). The PR title starts with `RECORD:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
