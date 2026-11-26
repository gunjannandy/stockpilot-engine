# SKELETON: Walking skeleton, code half: contract generator, Zod to JSON Schema, the Ping screen and the Ping Job

## Ticket

Key `SKELETON`, wave 0, machine **work**. Private parent: gunjannandy/stockpilot#135. Follow `work/README.md`.

Blocked by: MOVE

## What to build

The code half of the walking skeleton (SKELAPI is the API and pipeline half).
- A generator turns v2's `schemas/live-contract.json` into the first Zod files, one per area, with the index generated at build time and git-ignored. Drop the job kinds the spec drops (`weekly_review`, `snooze`, `dismiss`, `learned_forget`, `long_term_mark`, `rerun`, `feedback_read`).
- A second generator emits JSON Schema from the Zod package, and a typed API client for the web. The Python validates every row it writes against the JSON Schema (`py/stockpilot/io/core/`).
- The Python heartbeat library (running version, last success, last error, expected beat).
- A "Ping" button on one React screen (Vite, TanStack Router and Query) and a Python Ping Job that writes one row through the ingest door. Both are tested against a mock of the contract. SKELAPI makes the path live.

**Machine: work.**

## Acceptance criteria

- [ ] The generators run in CI and their output is not committed
- [ ] The Ping screen and the Ping Job pass their tests against the contract mock
- [ ] A Python row that breaks the JSON Schema fails its test

## Owned paths

- `contract/src/core/**`
- `tools/contract-gen/**`
- `web/src/main.tsx`
- `web/src/ping/**`
- `py/stockpilot/io/core/**`
- `py/stockpilot/jobs/ping/**`
- `py/stockpilot/heartbeat/**`

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/SKELETON`. The PR title starts with `SKELETON:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
