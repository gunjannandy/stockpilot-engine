# ADMINPROTO: Admin prototype round on a preview page

## Ticket

Key `ADMINPROTO`, wave 1, machine **work**. Private parent: gunjannandy/stockpilot#149. Follow `work/README.md`.

Blocked by: SKELETON

## What to build

Admin is the one screen with no approved design: v2's Health, Settings and Jobs merge into one place. Build a throwaway prototype on a `preview/ADMINPROTO` page with made-up data (prototypes are preview pages, never artifacts): Needs you, how fresh the data is, recent job runs with step trails and Try again, problems, settings (Budget and Target allocation for the owner, Pause releases, pause per job kind, feature flags, secret expiry, D1 size and writes, usage counts), and "Waiting for you" with screenshots beside the prototype, a preview link and Approve. Self-audit with real screenshots at 1440, 1100 and 400 px in both themes, then ask the owner. Close when the owner approves; ADMIN builds the real screen from it. Story 98 is checked by ADMIN.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `legacy/web/public/screens/jobs.js`
- `legacy/web/public/app.js (settings and health tabs)`

## Acceptance criteria

- [ ] The owner approves the prototype on this issue (record his words)

## Owned paths

- `web/src/prototypes/admin/**`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/v2/shots/jobs-*`, `docs/prototypes/ui/r10/`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/ADMINPROTO` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/ADMINPROTO` (and `preview/ADMINPROTO` to show it). The PR title starts with `ADMINPROTO:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
