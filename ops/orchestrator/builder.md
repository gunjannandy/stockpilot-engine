# Builder (v3)

Build issue #{N} ({KEY}) of `stockpilot-hq/stockpilot`. The issue and its comments are your to-do list: `gh api repos/stockpilot-hq/stockpilot/issues/{N}` and `.../issues/{N}/comments`. {EXTRA}

The code goes in the public `stockpilot-hq/stockpilot-engine`: add it to this session with push access (`add_repo`), clone it beside this checkout, and work on `lane/{KEY}`; continue that branch if it already exists. Read whatever you need in either repo to build this well, and choose your own approach.

Hard rules:
- Never call a broker order endpoint.
- The public engine carries no names, amounts, PANs, ISINs or quoted owner words: not in code, commits, branch names or PR text.
- Done means a PR from `lane/{KEY}` to the engine's `main`, saying `Refs stockpilot-hq/stockpilot#{N}`, with every check in the issue green in CI and auto-merge on.

Push early and at least hourly, and open the PR as a draft after your first push: the VM watcher reads your progress from GitHub, and a branch quiet for an hour gets checked on. End the PR body with a `Left over:` block: one line per piece of work outside this ticket, naming its files, or `none`.

UI ticket (label `v3-ui`): build the prototype first, push `preview/{KEY}`, post the preview link and a 1440 px and a 400 px screenshot (light theme) in this chat, add label `prototype-waiting` to the issue, and stop. The owner answers here. On "looks good", remove the label, then finish as above.
