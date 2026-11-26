# MODELNOTES: Fund calls and fund Analyse, post-mortems on missed calls, and the nightly portfolio note

## Ticket

Key `MODELNOTES`, wave 3, machine **work**. Private parent: gunjannandy/stockpilot#170. Follow `work/README.md`.

Blocked by: MODELS, FUNDS, RECORD, PORTFOLIO, CHECKS3

## What to build

Funds get the same rigour as stocks: port the Fund call (Keep, Add, Stop adding, Switch, Review; a Switch only with tax, exit load and yearly cost saved shown; ADR 0007) as a public model Job on MODELS' Runner, and Analyse on any fund. A short post-mortem on each missed Call at its 3-month score, one row per miss. The nightly portfolio note (deeper on Saturday) comes from a private Claude cloud scheduled task that reads a summary route behind its own key and writes back through the API; no model elsewhere sees holdings.

Here: the Fund call (keep `fundcall.py`) and fund Analyse as a public model Job, and the post-mortem Job, on fakes. The portfolio-note scheduled task, its key and the summary route are API3A's.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/fundcall.py`
- `docs/adr/0007-fund-forecaster.md`
- `schemas/fund_forecast.schema.json`
- `py/tests/test_fundcall.py`

## Acceptance criteria

- [ ] Fund call and post-mortem Jobs pass on the fake model

## Owned paths

- `py/stockpilot/jobs/fundcall/**`
- `py/stockpilot/jobs/postmortem/**`

## Owner's Approve

This ticket changes money, tax, numbers or forecast rules: do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/MODELNOTES`. The PR title starts with `MODELNOTES:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
