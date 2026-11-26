# RETIRE: Retire every v2 path in the engine and leave short agent docs

## Ticket

Key `RETIRE`, wave 3, machine **work**. Private parent: gunjannandy/stockpilot#180. Follow `work/README.md`.

Blocked by: CUTOVER

## What to build

Delete `legacy/` (v2 web, v2 workflows) and the old live-contract file, each with a check that the path answers "gone" or is absent: the KV queue (`/api/queue`, `/api/vm/*`), the v2 API (`/api/v2/*`). Leave a short `CLAUDE.md` of pointers, an updated `GLOSSARY.md` (drop Tick, Rerun, Request, Self-heal; add News impact, Heartbeat, Promise, Leftover, Ingest door).

**Machine: work.**

Stories: 151, 153 (numbers from the spec).

## Acceptance criteria

- [ ] `C-151-1` (production health): each retired path answers gone or is absent
- [ ] `C-153-1` (unit): doc check: pointers resolve, ADRs indexed

## Owned paths

- `legacy/**`
- `GLOSSARY.md`
- `CLAUDE.md`

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/RETIRE`. The PR title starts with `RETIRE:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
