# MODELS: Analyse in 5 minutes, fund calls, post-mortems, nightly notes

Status: building

## Done
- Analyse Job `py/stockpilot/jobs/analyse/` (`brief.py` public-only brief and private-field lock, `answer.py` answer checks, `__init__.py` run), prompt `py/stockpilot/prompts/analyse.md`, workflow `.github/workflows/analyse.yml` (protected `models` environment, main only).
- Analyse API `api/src/analyse/` (Job-only inputs read, call door with Bengali check, newest-call read, press route that dispatches at once, migration), contract `contract/src/analyse/analyse.ts`.
- Checks: C-037-1, C-038-1, C-039-1, C-170-2 (`checks/`), tests in `py/tests/analyse/` and `api/src/analyse/analyse.test.ts`.
- C-037-2 (Analyse promise measured daily) already exists in `api/src/promises/`.

## Next
- [ ] Bench: `py/stockpilot/jobs/bench/` (about 30 made-up past briefs with outcomes, form and verdict scoring, Haiku comparison report, pause gate), `.github/workflows/bench.yml`, checks C-130-1, C-131-1.
- [ ] Fund Analyse and fund call Jobs `py/stockpilot/jobs/fundcall/` (C-077-1).
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

## Blocked
- none
