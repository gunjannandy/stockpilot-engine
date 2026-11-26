# FIXTURES: Fake-data generator and the golden-day replay

## Ticket

Key `FIXTURES`, wave 1, machine **work**. Private parent: gunjannandy/stockpilot#141. Follow `work/README.md`.

Blocked by: MOVE, CHECKS1

## What to build

Build the fake-data generator (stocks, funds, prices, corporate actions, news, holdings, trades, lots, RSU vests, documents in the real layouts); its output passes the contract. v2's `tests/fakes.py` and fixtures are the start. Python stays (§13 Q1), so there are no known-good outputs to produce: the existing suites are the guard, and they must also pass on the generator's output. Record one made-up market day and add a golden-day replay to CI that runs the Jobs over it and compares the outputs.

**Machine: work.**

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/tests/fakes.py`
- `py/tests/fixtures/`
- `py/tests/build_fixture_site.py`
- `py/tests/conftest.py`
- `py/tests/fake_model.py`
- `py/tests/fake_worker.py`

Stories: 138, 139, 140 (numbers from the spec).

## Acceptance criteria

- [ ] `C-138-1` (unit): generator output passes the contract
- [ ] `C-139-1` (unit): replay produces the recorded outputs
- [ ] `C-140-1` (unit): the Python domain suites pass on the generator's output

## Owned paths

- `tools/fake/**`
- `py/tests/golden-day/**`

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/FIXTURES`. The PR title starts with `FIXTURES:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
