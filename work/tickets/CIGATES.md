# CIGATES: CI gates: privacy, never-order, check-files rule, trace rule, baselines, budgets, Renovate

## Ticket

Key `CIGATES`, wave 1, machine **work**. Private parent: gunjannandy/stockpilot#140. Follow `work/README.md`.

Blocked by: MOVE, CHECKS1

## What to build

Make the public repo's `main` safe for auto-merge on green. Required checks:
- privacy: every public PR's diff, title and body is scanned for names, rupee amounts, PANs and ISINs (v2's deny-list scan in `publish.py` is the start; the list stays in the private repo and is passed in by the workflow);
- never-order: fails on any broker order endpoint anywhere in code;
- workflow trigger rule: public model Jobs start only on schedule or by a Cloudflare dispatch, never on fork PRs; the Claude token sits in a protected `models` environment usable from `main` only;
- check-files rule: a PR that changes `checks/` without the planner's label fails; trace rule: a story in `trace.csv` with no check fails;
- screenshot baseline: once a screen is approved its screenshots become the baseline, and a diff fails;
- accessibility (axe) and performance budgets (bundle size, throttled-phone load);
- Renovate config: patch updates merge on green by themselves.

Derive `checks/status.json` (pending until a check first passes on `main`) by generator; builders never edit `checks/`.

Also: an **Approve-paths rule**. Any PR touching code a private Job runs with private secrets (private Job entry points, readers, lots, tax), `.github/workflows/**`, or a model Job's entry point waits for the owner's Approve, whichever machine wrote it. The privacy deny-list stays in the private repo and is passed in as a secret; build and test the gate with a made-up list.

**Machine: work.** `ci.yml` uses no secret except the deny-list, and this ticket's PR itself waits for the owner's Approve.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/publish.py`
- `py/tests/test_publish.py`
- `legacy/web/tests/e2e-t33.mjs`

Stories: 70, 123, 133, 134, 135, 136, 141 (numbers from the spec).

## Acceptance criteria

- [ ] `C-070-1` (unit): never-order check fails any order endpoint in code
- [ ] `C-123-1` (unit): workflow check rejects other triggers
- [ ] `C-133-1` (unit): privacy check catches planted fixtures
- [ ] `C-134-1` (unit): checks-label and trace rules
- [ ] `C-135-1` (screenshot): baseline diff fails on change
- [ ] `C-136-1` (preview e2e): axe passes; bundle and throttled-phone load under budget
- [ ] `C-141-1` (unit): Renovate config present and valid

## Owned paths

- `.github/workflows/ci.yml`
- `tools/gates/**`
- `renovate.json`
- `tools/check-status/**`

## Owner's Approve

This ticket changes money, tax, numbers or forecast rules: do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/CIGATES`. The PR title starts with `CIGATES:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
