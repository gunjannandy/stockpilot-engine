# CHECKS1: Write wave 1's acceptance checks as failing tests

## Ticket

Key `CHECKS1`, wave 0, machine **work**. Private parent: gunjannandy/stockpilot#139. Follow `work/README.md`.

Blocked by: MOVE

## What to build

Write every check of every wave-1 ticket (their ids and words are in each ticket's acceptance list) as real tests under `checks/<check-id>.*`, failing until the feature exists. Python checks use pytest, TypeScript checks Vitest or Playwright (preview e2e in mock mode, then real preview). Production-health checks are small HTTP probes that read only green or red. A check is "pending" until it first passes on `main`; that status is derived into `checks/status.json` by CI, so no builder edits `checks/`. This ticket carries the planner's label.

**Machine: work.**

## Acceptance criteria

- [ ] Every wave-1 check id has a test file under checks/
- [ ] Each new check fails on today's main for the right reason

## Owned paths

- `checks/**`

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/CHECKS1`. The PR title starts with `CHECKS1:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
