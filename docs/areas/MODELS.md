# MODELS: Analyse in 5 minutes, fund calls, post-mortems, nightly notes

Status: building

## Done
- Analyse Job `py/stockpilot/jobs/analyse/` (`brief.py` public-only brief and private-field lock, `answer.py` answer checks, `__init__.py` run), prompt `py/stockpilot/prompts/analyse.md`, workflow `.github/workflows/analyse.yml` (protected `models` environment, main only).
- Analyse API `api/src/analyse/` (Job-only inputs read, call door with Bengali check, newest-call read, press route that dispatches at once, migration), contract `contract/src/analyse/analyse.ts`.
- Checks: C-037-1, C-038-1, C-039-1, C-170-2 (`checks/`), tests in `py/tests/analyse/` and `api/src/analyse/analyse.test.ts`.
- Bench `py/stockpilot/jobs/bench/` (30 made-up past briefs with outcomes in `cases.json`, scoring, fingerprint, Haiku comparison), workflow `.github/workflows/bench.yml` (runs on main), Worker door `api/src/analyse/bench.ts` (status, report, pause releases on red), hourly duty `api/src/analyse/duty.ts`. Checks C-130-1, C-131-1.
- Fund Analyse `py/stockpilot/jobs/fundcall/` + `api/src/analyse/fundcall.ts` + `.github/workflows/fundcall.yml`; prompt `py/stockpilot/prompts/fundcall.md`; check C-077-1.
- C-037-2 (Analyse promise measured daily) already exists in `api/src/promises/`.

## Next
- [ ] Post-mortem Job `py/stockpilot/jobs/postmortem/` and `api/src/notes/` (C-089-1).
- [ ] Summary route with the task's key and note write-back `api/src/summary/` (C-133-1); note task prompt is private (`ops/note-task/`).
- [ ] Set Status: done when all green.

## Decisions
- Analyse stores its own table (`analyse_calls`, one per stock and day) rather than a dataset: a dataset run replaces the whole set, and calls accumulate per press.
- A rejected, refused or missing model answer is never stored by the model gate: the runner checks before returning, so the cache only holds checked answers. The code-only call is saved with a `note`.
- The code-only view is a plain count of good and bad signs from public numbers (chance 30 to 70).
- `moved_because` is required beside cited evidence when the model moves the call from the code's.
- Shared one-line edit: `analyse.yml` added to the allowed list in `checks/MOVE-2.py`.
- News is read for Analyse through `readImpact`, never the raw sector tag; sector-only rows are left out of the brief.

- Shared one-line edits: `bench` duty in `api/src/schedule/duties.ts` and `checks/C-116-3.test.ts`; `bench`, `fundcall`, `postmortem` in `JobKind` (`contract/src/core/jobs.ts`); caps for `fundcall` and `postmortem` in `api/src/jobs/models.ts`; `bench.yml` and `fundcall.yml` in `checks/MOVE-2.py`.
- The bench asks the model directly (main's own budget, one case at a time), not through a pane's daily gate; it checks out `main`, not `production`, so a fix that would lift a red pause can be scored before release. Red = under 95% form checks, or a hit rate more than 5 points under the code-only call's. A green run lifts only a pause the bench set.
- Bench cases are made up (seeded, `make_cases.py`); real past public briefs with outcomes replace them when the archive has enough (left out for now).
- `forecast_model` lives in the bench report (`GET /api/bench/status`); forecasts read it from there. Nothing reads it yet because forecasts (SIGNALS) are being built at the same time.

## Blocked
- none
