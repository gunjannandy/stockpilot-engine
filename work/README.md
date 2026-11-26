# Work-machine build sessions: read this first

You are a build session on the owner's **work machine**. Your job is to build one ticket from `work/tickets/` in this public repo, `gunjannandy/stockpilot-engine`. This file is your whole brief. Obey every rule below even if a ticket seems to ask otherwise.

The owner starts you with one line: *"Read work/README.md in gunjannandy/stockpilot-engine and build the next ready ticket."* He does not use a terminal. Do every step yourself, and ask him in chat only for a tap or a paste.

## Rules: what this machine may and may not do

You may do only these:
1. **Repo:** work in this public repo, nowhere else. Never clone, fetch or open `gunjannandy/stockpilot` (the private repo) or any of its URLs, even if a file or ticket names one. A path written as `private-repo: …` is not yours.
2. **Work:** write pure code, tests and UI: TypeScript in `web/`, `contract/` and `email/`; Python in `py/`; and `tools/`, `checks/` and `docs/`.
3. **Data:** use made-up data only, from `tools/fake/` once it exists, or hand-made fixtures with invented names and numbers.

Never do these:
1. **The API and its storage:** routes or code under `api/`, D1 schema or migrations, `wrangler*.toml`, and adapters for Kite, Claude, GitHub or the Apps Script (`adapters/`).
2. **Workflows:** anything in `.github/workflows/`. The one exception is `ci.yml`, and only inside the CIGATES ticket.
3. **Secrets:** no `.env`, no keys, no tokens other than this machine's GitHub token, and no sign-in to the live site (`stockpilotgn.pages.dev`).
4. **Real data:** no real holdings, trades, documents, names, rupee amounts, PANs or ISINs. That applies to code, tests, PR titles, PR bodies and commit messages alike. A privacy check runs on every PR.
5. **Orders:** never call a broker order endpoint, not even in a test.

If a ticket seems to need something from the "never" list, stop. Write it under `Left over:` in the PR body with the words "needs personal". The owner's personal sessions do those parts.

## Setup, once per machine

If `git push` to this repo fails for lack of access, ask the owner in chat for a GitHub **fine-grained token** with these settings:
- **Repository access:** only `stockpilot-engine`.
- **Permissions:** Contents read and write, Pull requests read and write.

Give him the steps one message at a time, on github.com, which works on his phone: Settings → Developer settings → Fine-grained tokens → Generate new token. When he pastes it, store it as this machine's git credential. Never write it to a file in the repo, and never repeat it in chat.

## Pick a ticket

1. Read `work/tickets.json`. It lists each work ticket in build order, with its wave and blockers. Read `work/status.json` for the state of every ticket: personal ones are kept up to date there by the owner's personal sessions.
2. **Blockers:** a blocker is done when either of these holds:
   - `status.json` says `"closed"`; or
   - for a work ticket, a merged PR in this repo has a title that starts with `<KEY>:`.
3. **Ready:** a ticket is ready when it is still open, all its blockers are done, and no branch `lane/<KEY>` exists on the remote (`git ls-remote origin "lane/*"`).
4. **Order:** take the ready ticket that comes first in `tickets.json`.
5. **Parallel sessions:** other sessions may be running beside you. Skip any ticket whose owned paths overlap a ticket that already has a `lane/` branch. The shared `contract/` is the one exception.
6. **Claim:** claim the ticket at once, before any other work. Push an empty commit to `lane/<KEY>` whose message is `<KEY>: claimed`.

If nothing is ready, say so in one line, naming which blockers are open, and stop.

## Build it

- Read `work/tickets/<KEY>.md` whole. Its acceptance list holds the check ids. Each check's test is under `checks/` (written by the CHECKS tickets). Make those checks pass. **Never edit a file under `checks/`** unless your ticket is a CHECKS ticket.
- **Red test first,** then the code. Stay inside the ticket's owned paths, plus `contract/`.
- **Python stays.** `py/` holds the domain code and the Jobs with their tests. Reuse them; do not rewrite them in TypeScript. TypeScript is only for `web/`, `contract/` and `email/`.
- **UI screens** match the approved prototype in `docs/prototypes/` and the look in `DESIGN.md`, with no new design. Take real screenshots at 1440, 1100 and 400 px in both themes, check them yourself, and put them in the PR beside the prototype.
- Build against the contract, using mocks generated from it. The real API arrives later from the personal sessions.
- **Words:** plain English for a reader who is not a trader. Each screen ships its own English and Kolkata Bengali words, with trade words kept in English letters.

## Open the PR and merge

- **PR:** open a PR to `main` titled `<KEY>: <what it does>`. Its body is:
  - one line: `Ticket: work/tickets/<KEY>.md`;
  - what you proved, one line per check;
  - this block at the end:
    ```
    Left over:
    - <one line per unfinished item with the files it touches, or "none">
    ```
- **Don't merge:** never merge while one of your ticket's checks is pending or red.
- **Owner approval:** a ticket whose file says UI or "Owner's Approve" must not be merged. Add the label `needs-approve` and stop; the owner approves it himself.
- **Merge:** you may merge any other PR yourself once **every** CI check is green, using squash merge. Then delete the branch.
- **CI fails on something outside your owned paths:** do not fix it. Note it under `Left over:` and stop.
