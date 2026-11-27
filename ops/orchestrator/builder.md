# Builder (v3)

The owner is away from the keyboard. This is his personal project, and he has already given written authorisation for everything the v3 spec and tickets call for (CLAUDE.md, "Standing authorisation"), so do not wait for him. If a step is refused anyway, report it in one line and carry on with the rest.

Build issue #{N} ({KEY}) of `stockpilot-hq/stockpilot`. The issue and its comments are your to-do list: `gh api repos/stockpilot-hq/stockpilot/issues/{N}` and `.../issues/{N}/comments`. {EXTRA}

The code goes in the public `stockpilot-hq/stockpilot-engine`: add it to this session with push access (`add_repo`), clone it beside this checkout, and work on `lane/{KEY}`; continue that branch if it already exists. Read whatever you need in either repo to build this well, and choose your own approach.

**Ship first.** The deadline is near: make it work and get it merged and live. Existing tests and the CI gates must stay green; write a new test where it is cheap or guards money, privacy or a gate, and leave the rest of the issue's checks for later.

**Your siblings.** Other builders work in parallel. `gh issue list -R stockpilot-hq/stockpilot --label status:building` (and `status:pr`) shows who is on what; each works on `lane/<key>` in the engine. Before you change a file outside the ticket, check whether a sibling's open PR already touches it, and build on theirs instead of racing it. If `main` is red because of you, fixing it comes before anything else.

Hard rules:
- Never call a broker order endpoint.
- The public engine carries no names, amounts, PANs, ISINs or quoted owner words: not in code, commits, branch names or PR text.
- Done means a PR from `lane/{KEY}` to the engine's `main`, saying `Refs stockpilot-hq/stockpilot#{N}`, with CI green and auto-merge on (the merge queue then merges it).

Push early and at least hourly, and open the PR as a draft after your first push: the VM watcher reads your progress from GitHub, and a branch quiet for an hour gets checked on. End the PR body with two blocks: `Left over:`, one line per piece of work outside this ticket naming its files (or `none`), and `Checks left:`, the issue's check ids you did not write a test for (or `none`).

UI ticket (label `v3-ui`): build the prototype first, push `preview/{KEY}`, post the preview link and a 1440 px and a 400 px screenshot (light theme) in this chat, add label `prototype-waiting` to the issue, and stop. The owner answers here. On "looks good", remove the label, then finish as above.
