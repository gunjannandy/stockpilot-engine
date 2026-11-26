# FEEDBACK: Feedback: one box, status per ask, owner's review, Reviewed becomes a ticket by code

## Ticket

Key `FEEDBACK`, wave 2, machine **work**. Private parent: gunjannandy/stockpilot#162. Follow `work/README.md`.

Blocked by: SHELL, CHECKS2

## What to build

The father writes anything in one box and sees Received at once. Each Ask shows its status (Received, Reviewed, Planned, Being built, Done, Not planned) and its Job. The owner, and only the owner, opens a dropdown, writes his understanding and sets Reviewed or Not planned. Reviewed makes one `ready-for-agent` issue in the private repo quoting both texts, by Worker code with no model (v2's `feedback_read` model split and "not what I meant" are not ported). The Ask's status follows its ticket to Done (v2's `ask_tickets.py` logic). Feedback unreviewed for 24 hours opens an issue so GitHub emails the owner. Feedback status rows are append-only.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `legacy/web/public/screens/feedback.js`
- `legacy/web/functions/api/v2/feedback.js`
- `legacy/web/functions/api/v2/asks/`
- `py/stockpilot/feedback.py`
- `py/stockpilot/ask_tickets.py`
- `py/stockpilot/asks.py`
- `legacy/web/test/feedback-screen.test.js`

Stories: 91, 92 (numbers from the spec).

## Acceptance criteria

- [ ] `C-091-1` (preview e2e): feedback box sends and shows Received
- [ ] `C-091-2` (screenshot): Feedback beside the prototype
- [ ] `C-092-1` (preview e2e): status and job shown per ask

## Owned paths

- `web/src/screens/feedback/**`
- `web/src/words/feedback.*`
- `contract/src/feedback.ts`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/v2/shots/feedback-*`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/FEEDBACK` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/FEEDBACK` (and `preview/FEEDBACK` to show it). The PR title starts with `FEEDBACK:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
