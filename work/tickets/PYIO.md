# PYIO: Python I/O adapter: Parquet history, private tables by job key, writes through the ingest door; Job entry points

## Ticket

Key `PYIO`, wave 1, machine **work**. Private parent: gunjannandy/stockpilot#142. Follow `work/README.md`.

Blocked by: SKELETON, CHECKS1

## What to build

Replace the DuckDB store with one adapter so every Python Job runs the same on Actions, in Docker and in tests:
- read price history from the Parquet files on the engine's releases (DuckDB in memory, nothing persisted);
- read private tables only through a job-key route on the API (the route is API1's); a fake of that route for tests;
- write only through the ingest door, every row validated against the contract's JSON Schema, carrying source, fetch time and "as of";
- one entry point per Job kind (`python -m stockpilot.jobs.<kind>`), progress lines, heartbeat, every outside call through one injectable object.
Port each Job's reads and writes from `store.py` onto it; delete `store.py`.

**Machine: work.** Fakes only; the real routes and keys are the personal API tickets'.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/store.py`
- `py/stockpilot/jobrun.py`
- `py/stockpilot/journal.py`
- `py/stockpilot/machine.py`

## Acceptance criteria

- [ ] Every Job kind runs on the fake adapter in CI
- [ ] store.py is gone and no module imports duckdb outside io/

## Owned paths

- `py/stockpilot/io/**`
- `py/stockpilot/jobs/entry/**`

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/PYIO`. The PR title starts with `PYIO:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
