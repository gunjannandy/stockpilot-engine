# MODELS: Analyse in 5 minutes on public data, Bengali in the same call, and the Haiku vs Sonnet forecast bench

## Ticket

Key `MODELS`, wave 3, machine **work**. Private parent: gunjannandy/stockpilot#169. Follow `work/README.md`.

Blocked by: CALLS, CHECKS3

## What to build

The father asks Analyse on any stock and gets a Call within 5 minutes, with a progress bar that knows the usual time. Port the Brief builders (the dossier and its three blocks, the readiness list) and the Runner, keeping holdings out: the Brief holds public data only, and code adds the tax and "if you act" lines afterwards. Public model Jobs run in the engine's Actions, started only on schedule or by a Cloudflare dispatch. The model writes Bengali in the same call as the English; an answer without Bengali is rejected. The model is set per job kind in config, Haiku by default; the Skeptic runs only near a decision line.

The forecast test bench: about 30 past public Briefs with outcomes, scored in CI on every prompt, model or method change. It doubles as the comparison: Haiku keeps forecasts only at ≥95% of form checks and ≥80% verdict agreement, else forecasts and Analyse use Sonnet. Record the result in an ADR. House rules and the weekly prompt review are not ported.

In Python: keep `dossier.py`, `dossier_blocks.py`, `calls/brief.py` and `calls/runner.py`; the Runner calls the model through an injectable client (the real Claude adapter and the `models` environment are API3A's). Model Jobs run `claude` with tools off and JSON output only. The bench runs on `main` after a prompt, model or method change; red pauses releases.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/dossier.py`
- `py/stockpilot/dossier_blocks.py`
- `py/stockpilot/calls/brief.py`
- `py/stockpilot/calls/runner.py`
- `py/stockpilot/modeljson.py`
- `py/stockpilot/readiness.py`
- `py/stockpilot/sources/headlines.py`
- `py/stockpilot/sources/news.py`
- `prompts/`
- `py/tests/fixtures/dossier/`

Stories: 34, 121, 122 (numbers from the spec).

## Acceptance criteria

- [ ] `C-034-1` (preview e2e): Analyse runs to a call on made-up data
- [ ] `C-121-1` (main run): comparison report: ≥95% form checks, ≥80% verdict agreement, else Sonnet for forecasts
- [ ] `C-122-1` (main run): bench scores on main after a prompt, model or method change; red pauses releases

## Owned paths

- `py/stockpilot/jobs/analyse/**`
- `py/stockpilot/jobs/brief/**`
- `config/models.*`
- `tools/bench/**`
- `contract/src/models.ts`

## Owner's Approve

This ticket changes money, tax, numbers or forecast rules: do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/MODELS`. The PR title starts with `MODELS:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
