# EMAIL: Morning email HTML: the owner's full version and the father's short one, as a pure renderer

## Ticket

Key `EMAIL`, wave 3, machine **work**. Private parent: gunjannandy/stockpilot#174. Follow `work/README.md`.

Blocked by: TODAY, FEEDBACK, CHECKS3

## What to build

A pure TypeScript renderer (`email/`) that turns the morning summary (contract type) into styled HTML: the owner's version (today's call, what changed, the three promises, each part's status, the last 24 hours of Jobs, freshness, releases, feedback waiting, usage left, progress against the cutover target until cutover; no Sync link) and the father's (the call line and what changed). When health is unreachable it renders that line. Snapshot tests on made-up summaries. Sending is EMAILWIRE's.

**Machine: work.**

Stories: 108 (numbers from the spec).

## Acceptance criteria

- [ ] `C-108-1` (unit): unreachable health renders that line

## Owned paths

- `email/**`

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/EMAIL`. The PR title starts with `EMAIL:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
