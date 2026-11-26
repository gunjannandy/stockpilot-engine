# JOBSCORE: Jobs that cannot double up, the market calendar, model budget and cache, provenance on every row

## Ticket

Key `JOBSCORE`, wave 1, machine **work**. Private parent: gunjannandy/stockpilot#148. Follow `work/README.md`.

Blocked by: PYIO, CHECKS1

## What to build

Every Job after this one is a plain Node command on this runtime (v2's `jobrun.py`, `journal.py` and `machine.py` are the shape: one entry point, progress lines, every outside call through one injectable object so tests use fakes):
- a unique key (kind, subject, day): a second identical Job is refused; one lock per kind; retry with backoff; an expected time from past runs for progress bars; a pause switch per kind (a paused kind starts no Job);
- a daily model budget per kind: past the cap the Job is refused and the screen shows the last forecast with "next update tomorrow"; an answer cache for the same Brief, model and day;
- the ingest door refuses rows without source, fetch time and "as of".

One market-calendar and corporate-actions module (holidays, special sessions, splits, bonuses, symbol changes, delistings) that every schedule follows, ported from `exchange.py` and the corporate-action parsers. Times stored in UTC, shown in IST; the freshness rule holds across holidays.

In Python: the runtime wraps PYIO's entry points; the market calendar stays Python (`exchange.py`, the corporate-action parsers) with a small TypeScript twin of the freshness rule for the Worker, tested on the same fixtures.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/jobrun.py`
- `py/stockpilot/jobs/due.py`
- `py/stockpilot/journal.py`
- `py/stockpilot/machine.py`
- `py/stockpilot/sources/exchange.py`
- `py/stockpilot/trades/corporate_actions.py`
- `py/stockpilot/trades/corporate_actions_feeds.py`
- `legacy/web/functions/api/v2/jobs/`
- `legacy/web/lib/v2/handlers.js`

Stories: 114, 115 (numbers from the spec).

## Acceptance criteria

- [ ] `C-114-1` (unit): calendar and adjustments from fixtures
- [ ] `C-115-1` (unit): freshness rule across holidays

## Owned paths

- `py/stockpilot/jobs/runtime/**`
- `py/stockpilot/domain/calendar/**`
- `contract/src/jobs.ts`

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/JOBSCORE`. The PR title starts with `JOBSCORE:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
