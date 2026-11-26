# OPS: Operations code: dependency checks and fallbacks, the D1 archive Job, the restore-drill compare, runbooks

## Ticket

Key `OPS`, wave 3, machine **work**. Private parent: gunjannandy/stockpilot#173. Follow `work/README.md`.

Blocked by: ADMIN, MODELS, CHECKS3

## What to build

The code half of operations, on fakes: a written fallback and a check for each outside dependency (NSE, BSE, Yahoo, AMFI, Google News, Kite, Claude usage, GitHub Actions, Cloudflare limits); the Job that archives old D1 rows to Parquet before the 500 MB cap; the backup and restore-drill compare logic (port `backup.py` and `vault.py` as pure functions; the workflows and the vault are OPSAPI's).

**Machine: work.**

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/backup.py`
- `py/stockpilot/vault.py`
- `py/tests/test_backup.py`
- `py/tests/test_drill.py`

## Acceptance criteria

- [ ] Each dependency check and the archive Job pass on fakes
- [ ] The restore-drill compare reports a planted mismatch

## Owned paths

- `py/stockpilot/jobs/deps/**`
- `py/stockpilot/jobs/archive/**`
- `py/stockpilot/ops/**`
- `docs/ops/fallbacks.md`

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/OPS`. The PR title starts with `OPS:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
