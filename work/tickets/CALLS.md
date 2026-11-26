# CALLS: Call card and pane from the nightly screen and forecast, append-only, with compare

## Ticket

Key `CALLS`, wave 2, machine **work**. Private parent: gunjannandy/stockpilot#154. Follow `work/README.md`.

Blocked by: STOCK, CHECKS2

## What to build

Every stock gets one unambiguous Call the father can judge. A nightly public Job runs PORTFORECAST's Screen and Starting chance over every stock and PORTCALLS' decisions, and appends Calls and forecasts; screens read the latest row, never edit in place. The call card carries one verdict (Sell, Weak, Hold, Watch, Buy, Trim, No view yet), the chance it beats the Nifty with the sell and buy lines, why, what could go wrong, if you act, tax, we would buy if, sell at once if it falls to, it could rise to, levels and track, and the track-record line. The `reasoning` object (why we think what we think, in plain words, built by code) is ported here. Compare two stocks side by side, starting from similar companies. Analyse and model-written text arrive in MODELS.

**Machine: work.** Build the screens, the Python Jobs, the contract files and the tests. API routes, D1 schema, adapters (Kite, Claude, GitHub, Apps Script) and workflows are the matching API ticket's, on the personal account. Build against the contract with mocks generated from it; preview e2e checks run in mock mode in CI, and again on the real preview once the API ticket lands.

## v2 code to read or reuse

Python stays (decisions §13): `py/` is today's `src/stockpilot/` and `tests/` after MOVE, `legacy/` holds the v2 web code. Reuse the Python and its tests; rewrite only the web and API parts; do not carry over what the spec drops.

- `py/stockpilot/forecast.py`
- `py/stockpilot/reasoning.py`
- `legacy/web/functions/api/v2/calls/[symbol].js`
- `legacy/web/public/screens/stock.js`

Stories: 32, 42 (numbers from the spec).

## Acceptance criteria

- [ ] `C-032-1` (preview e2e): every call-card section renders
- [ ] `C-032-2` (screenshot): call pane beside the prototype
- [ ] `C-042-1` (preview e2e): compare view shows both stocks' facts and calls

## Owned paths

- `web/src/screens/call/**`
- `web/src/screens/compare/**`
- `web/src/words/call.*`
- `py/stockpilot/jobs/calls/**`
- `contract/src/calls.ts`

## Mockup

Match the approved prototype; no new design round. References: `docs/prototypes/v2/shots/stock-sk2-*`, `docs/prototypes/ui/r10/`. Look: `DESIGN.md`. Verdicts: `docs/prototypes/v2/README.md` (copy every verdict line for this screen into the PR). Push `preview/CALLS` when ready to show, self-audit real screenshots at 1440, 1100 and 400 px in both themes, and place them beside the prototype in the PR. Do not merge: add the label `needs-approve` and leave the PR open for the owner.

## How to work

- Read `work/README.md` first and obey it: public engine only, made-up data only, pure code, tests and UI; never the API, D1 schema, adapters, workflows, secrets or real data.
- Push `lane/CALLS` (and `preview/CALLS` to show it). The PR title starts with `CALLS:`; the body carries no names, amounts, PANs, ISINs or owner words.
- Red test first. Turn this ticket's checks under `checks/` green; never edit a check file.
- Touch only the owned paths above plus the shared contract. Each screen ships its own English and Bengali words. Each Job writes its heartbeat.
- Do not merge with one of this ticket's checks pending. End the PR body with `Left over:` and one line per unfinished item (or `none`).
