# INSTANT: Instant and honest opens: cached first paint, updating state, installable app, last-good banner, freshness

## Ticket

Key `INSTANT`, wave 1, machine **work**. Private parent: gunjannandy/stockpilot#147. Follow `work/README.md`.

Blocked by: SHELL, CHECKS1

## What to build

The page opens at once from the last data it saw (TanStack Query with a persisted cache), then refreshes quietly. When the page and the API disagree on `contract_version`, a calm "updating" state shows, never broken numbers. An installable app with its own icon and window shows the last data offline. When a hard check fails, the API serves the last good snapshot with its date and the page shows a banner; each data Job registers its hard checks with this mechanism (v2's `sp verify` split three ways, retro §7.3). The shell and Admin show when each source and the holdings were last updated, where "fresh" means the last trading day's close is in. The bundle holds no data; public data files pass through `/data/*` from the engine's release assets (browsers cannot read them directly: probe 2) with content-hashed names and year-long edge caching.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `legacy/web/public/live.js`
- `py/stockpilot/sources/public_files.py`
- `py/stockpilot/verify/report.py`
- `py/stockpilot/gaps.py`
- `legacy/web/functions/api/v2/views/[name].js`

Stories: 15, 16, 17, 21 (numbers from the spec).

## Acceptance criteria

- [ ] `C-015-1` (preview e2e): a second visit draws before the network answers
- [ ] `C-016-1` (preview e2e): a mismatched version shows the updating state
- [ ] `C-017-1` (preview e2e): manifest installs; offline load shows cached data
- [ ] `C-021-1` (preview e2e): freshness times shown in the shell and Admin

## Owned paths

- `web/src/data/**`
- `web/public/manifest*`
- `web/src/sw/**`

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/INSTANT`. The PR title starts with `INSTANT:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
