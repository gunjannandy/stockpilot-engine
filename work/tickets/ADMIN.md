# ADMIN: Admin: Needs you, freshness, job runs with Try again, Waiting for you with Approve, Pause releases, usage counts

## Ticket

Key `ADMIN`, wave 2, machine **work**. Private parent: gunjannandy/stockpilot#163. Follow `work/README.md`.

Blocked by: ADMINPROTO, JOBSCORE, CHECKS2

## What to build

Build Admin from the approved ADMINPROTO prototype: Needs you, how fresh the data is, recent job runs with step trails and Try again, problems, and settings (pause per job kind, feature flags; Budget and Target allocation live on PORTFOLIO's settings routes). "Waiting for you" lists each PR's screenshots beside the prototype, its preview link and an Approve button; Approve adds a label, and a required check accepts that label only when the button added it. A Pause releases switch stops promotion to `production`. Usage counts per screen and button, kept in our own D1.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `legacy/web/public/screens/jobs.js`
- `legacy/web/functions/api/v2/jobs/[id]/rerun.js`
- `py/stockpilot/jobs/doctor.py`

Stories: 98 (numbers from the spec).

## Acceptance criteria

- [ ] `C-098-1` (preview e2e): Admin sections render; Try again requeues
- [ ] `C-098-2` (screenshot): Admin beside its approved preview prototype

## Owned paths

- `web/src/screens/admin/**`
- `web/src/words/admin.*`
- `contract/src/admin.ts`

## Mockup

Match the approved prototype; no new design round. References: `the approved ADMINPROTO preview`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/ADMIN` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/ADMIN` (and `preview/ADMIN` to show it). The PR title starts with `ADMIN:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
