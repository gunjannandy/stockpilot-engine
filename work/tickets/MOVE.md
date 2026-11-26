# MOVE: Move the engine into the v3 layout by script; Python into py/ with CI green; VM code deleted

## Ticket

Key `MOVE`, wave 0, machine **work**. Private parent: gunjannandy/stockpilot#134. Follow `work/README.md`.

## What to build

Restructure `stockpilot-engine` into the v3 monorepo with a script (`tools/move/`), so the move is reviewable and rerunnable; the session reviews the result instead of moving files by hand.
- pnpm workspaces `contract`, `web`, `api` (empty for now), plus `py/` (uv) holding today's `src/stockpilot/` and `tests/`. Node 24, TypeScript strict, Biome, Vitest.
- **Python stays** (decisions §13 Q1). Delete the VM-only Python: `store.py` as state, `site.py`, `site_export/`, `vmqueue.py`, `jobs/{minute,ship,wire,vmjobs}.py`, `orchestrate/`, the `cli` entry points that only the VM used, and the tests of those. Keep every domain module and its tests: `analysis/`, `mechanical/`, `trades/`, `book/`, `calls/`, `costs.py`, `forecast_form.py`, `fundcall.py`, the sources.
- Make `py` CI green and under 5 minutes with `pytest-xdist` on the 4 cores. Today's two reds: `tests/jobs/test_ship_verify.py` reads a VM unit file (delete with `jobs/ship.py`), and the browser CLS budget at 1100 px (the v2 browser job moves to `legacy/` with the v2 web code).
- Move the 13 v2 workflows out of `.github/workflows/` into `legacy/workflows/` so no v2 Python job runs on schedule (v2 is frozen, decisions §12). Move v2 `web/` to `legacy/web/` (RETIRE deletes it).
- The domain checks this ticket owns pass when the existing suites run green in `py/`.

**Machine: work.** Pure code and tests in the public engine; no secrets.

Stories: 25, 31, 60, 61, 73, 86, 89, 140 (numbers from the spec).

## Acceptance criteria

- [ ] `C-025-1` (unit): breadth, trend and value bands from fixtures: the existing Python suite for this passes in py/ CI (no port)
- [ ] `C-031-1` (unit): forecast form and its checks: the existing Python suite for this passes in py/ CI (no port)
- [ ] `C-060-1` (unit): RSU logic: the existing Python suite for this passes in py/ CI (no port)
- [ ] `C-061-1` (unit): lots: the existing Python suite for this passes in py/ CI (no port)
- [ ] `C-073-1` (unit): made-up documents in the same layouts parse to known rows: the existing Python suite for this passes in py/ CI (no port)
- [ ] `C-086-1` (unit): scoring: the existing Python suite for this passes in py/ CI (no port)
- [ ] `C-089-1` (unit): own-record stats: the existing Python suite for this passes in py/ CI (no port)
- [ ] `C-140-2` (unit): mechanical forecast, base rates, screen, market health and levels: the existing Python suite for this passes in py/ CI (no port)
- [ ] `C-140-3` (unit): call decisions, sell kinds, what changed and unusual today: the existing Python suite for this passes in py/ CI (no port)
- [ ] `C-140-4` (unit): positions, units check, valuation, allocation and smallcase tags: the existing Python suite for this passes in py/ CI (no port)

## Owned paths

- `package.json`
- `pnpm-workspace.yaml`
- `biome.json`
- `py/pyproject.toml`
- `py/stockpilot/**`
- `py/tests/**`
- `tools/move/**`
- `legacy/**`

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/MOVE`. The PR title starts with `MOVE:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
