# PYDOMAIN: New numbers in Python: the dated tax-rules file, XIRR, concentration, Nifty -10%, 'calls like this'

## Ticket

Key `PYDOMAIN`, wave 1, machine **work**. Private parent: gunjannandy/stockpilot#143. Follow `work/README.md`.

Blocked by: MOVE, CHECKS1

## What to build

Beside the existing Python, with its suites still green:
- Turn `tax.py`'s `rules_for` into one dated tax-rules file: the 1961 Act before tax year 2026-27 and the Income-tax Act 2025 from it, with limits such as the ₹1.25 lakh exemption, so a law change is a one-file edit.
- XIRR for the portfolio and each Holding against the Nifty over the same cash flows, from hand-worked fixtures.
- Concentration by stock and sector, and a beta-based "Nifty falls 10%" shock.
- The grouping behind "our last 24 calls like this: 15 beat the Nifty" (which past Calls count as "like this", and the counts).
Every number here is computed by the nightly private Job and stored; the Worker never computes it.

**Machine: work.** Money and tax: the PR waits for the owner's Approve.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/analysis/tax.py`
- `py/stockpilot/costs.py`
- `py/stockpilot/trackrecord.py`

Stories: 33, 58, 59, 62, 63, 64, 67 (numbers from the spec).

## Acceptance criteria

- [ ] `C-033-1` (unit): similar-call grouping and counts from fixtures
- [ ] `C-058-1` (unit): tax engine: the existing Python suite for this passes in py/ CI (no port)
- [ ] `C-059-1` (unit): ITR pack: the existing Python suite for this passes in py/ CI (no port)
- [ ] `C-062-1` (unit): XIRR against hand-worked fixtures
- [ ] `C-063-1` (unit): concentration from fixtures
- [ ] `C-064-1` (unit): beta-based shock from fixtures
- [ ] `C-067-1` (unit): rules picked by date

## Owned paths

- `py/stockpilot/analysis/tax.py`
- `py/stockpilot/domain/returns/**`
- `py/stockpilot/domain/risk/**`
- `py/stockpilot/domain/track_line/**`
- `config/tax-rules.*`

## Owner's Approve

This ticket changes money, tax, numbers or forecast rules: do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/PYDOMAIN`. The PR title starts with `PYDOMAIN:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
