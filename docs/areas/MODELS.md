# MODELS: Analyse in 5 minutes, fund calls, post-mortems, nightly notes

Status: done

## Done
- Analyse Job `py/stockpilot/jobs/analyse/` (`brief.py` public-only brief and private-field lock, `answer.py` answer checks, `__init__.py` run), prompt `py/stockpilot/prompts/analyse.md`, workflow `.github/workflows/analyse.yml` (protected `models` environment, main only).
- Analyse API `api/src/analyse/` (Job-only inputs read, call door with Bengali check, newest-call read, press route that dispatches at once, migration), contract `contract/src/analyse/analyse.ts`.
- Checks: C-037-1, C-038-1, C-039-1, C-170-2 (`checks/`), tests in `py/tests/analyse/` and `api/src/analyse/analyse.test.ts`.
- Bench `py/stockpilot/jobs/bench/` (30 made-up past briefs with outcomes in `cases.json`, scoring, fingerprint, Haiku comparison), workflow `.github/workflows/bench.yml` (runs on main), Worker door `api/src/analyse/bench.ts` (status, report, pause releases on red), hourly duty `api/src/analyse/duty.ts`. Checks C-130-1, C-131-1.
- Fund Analyse `py/stockpilot/jobs/fundcall/` + `api/src/analyse/fundcall.ts` + `.github/workflows/fundcall.yml`; prompt `py/stockpilot/prompts/fundcall.md`; check C-077-1.
- Post-mortems: Job `py/stockpilot/jobs/postmortem/`, prompt, workflow `postmortem.yml`, Worker `api/src/notes/` (due calls scored against the Nifty 50, one row per missed call, Record read), contract `contract/src/notes/notes.ts`; check C-089-1.
- Nightly note: summary route `api/src/summary/` (raw rows behind `NOTE_TASK_KEY`), note write-back and read in `api/src/notes/`; check C-133-1.
- Words `web/src/words/analyse.*` and `notes.*` (English and Bengali), no panes.
- C-037-2 (Analyse promise measured daily) already exists in `api/src/promises/`.

## Next
- [ ] After merge: watch the first bench run (Haiku comparison, C-130-1, C-131-1) and the daily Analyse promise (C-037-2) in production.

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

- The one `models` duty (hourly) starts the bench (per IST hour) and the post-mortem Job (once a day when a Buy or Avoid has reached its three-month score unexplained); renamed from `bench` in `api/src/schedule/duties.ts` and `checks/C-116-3.test.ts`.
- Post-mortems cover stock calls from Analyse only (scored against the `NIFTY 50` history rows, hurdle ignored); fund post-mortems are left out until fund calls are scored. Other areas' calls join by writing to `analyse_calls` or by a later reader.
- A post-mortem always gets its row: a rejected or missing model answer leaves a code-written line (cause unknown).
- The nightly note key is the Worker secret `NOTE_TASK_KEY` (24 characters at least), header `x-task-key`; with none set both routes stay closed.

## Blocked
- cockpit: set the Worker secret `NOTE_TASK_KEY` and create the Claude scheduled task with its prompt in the private repo `ops/note-task/` (Haiku, deeper on Saturday; reads `/api/summary`, runs `money`, posts `/api/notes/nightly`).
- cockpit: confirm the `models` environment holds `CLAUDE_CODE_OAUTH_TOKEN` for `analyse.yml`, `fundcall.yml`, `postmortem.yml` and `bench.yml` (all main only); the first bench run after merge is the Haiku comparison and sets `forecast_model`.

Left over: browser call card adds the tax and "if you act" lines on the device (web/src/panes/analyse, designed in the UI review); real past briefs replace the made-up bench cases when the archive has them.

Chapter end: 1
