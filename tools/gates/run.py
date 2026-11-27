"""Run one CI gate. Usage: python tools/gates/run.py <privacy|never-order|workflow-triggers|contract-additive|trace|planner-label>

Prints problems (never matched text) and exits 1 on any. On the merge queue (no PR in the event) the PR-only gates pass:
the PR already passed them, and the queue's own run still has to finish green so `gate` is not skipped.
"""
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
from gates import contract_additive, never_order, planner_label, privacy, trace, workflow_triggers  # noqa: E402

SCHEMA_DIR = "contract/schema"  # where the contract generator writes JSON Schema
PRODUCTION_REF = "origin/production"


def git(*args):
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def event():
    path = os.environ.get("GITHUB_EVENT_PATH")
    return json.loads(Path(path).read_text()) if path else {}


def pr_of(ev):
    return ev.get("pull_request")


def base_sha(ev):
    pr = pr_of(ev)
    return pr["base"]["sha"] if pr else ev.get("merge_group", {}).get("base_sha") or ev.get("before") or "origin/main"


def api(path):
    req = urllib.request.Request(f"https://api.github.com{path}", headers={"Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}", "Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def gate_privacy(ev):
    deny = privacy.load_deny_terms(os.environ.get("PRIVACY_DENY_LIST"))
    pr = pr_of(ev) or {}
    diff = git("diff", "--unified=0", f"{base_sha(ev)}...HEAD")
    return [str(f) for f in privacy.scan_pr(pr.get("title"), pr.get("body"), diff, deny)]


def gate_never_order(ev):
    return [str(f) for f in never_order.scan_files(ROOT, never_order.tracked_files(ROOT))]


def gate_workflow_triggers(ev):
    return workflow_triggers.check_dir(ROOT / ".github/workflows")


def gate_contract_additive(ev):
    import tempfile
    exists = subprocess.run(["git", "rev-parse", "--verify", "-q", PRODUCTION_REF], cwd=ROOT, capture_output=True).returncode == 0
    if not exists or not git("ls-tree", "-r", "--name-only", PRODUCTION_REF, SCHEMA_DIR).strip():
        return []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(f"git archive {PRODUCTION_REF} {SCHEMA_DIR} | tar -x -C {tmp}", shell=True, cwd=ROOT, check=True)
        return contract_additive.compare_dirs(Path(tmp) / SCHEMA_DIR, ROOT / SCHEMA_DIR)


def gate_trace(ev):
    return trace.check_text((ROOT / "checks/trace.csv").read_text())


def gate_planner_label(ev):
    pr = pr_of(ev)
    if not pr:
        return []
    changed = git("diff", "--name-only", f"{pr['base']['sha']}...HEAD").split()
    main_files = git("ls-tree", "-r", "--name-only", pr["base"]["sha"], "checks/").split()
    if not planner_label.needs_label(changed, main_files):
        return []
    repo = os.environ["GITHUB_REPOSITORY"]
    events, page = [], 1
    while True:
        chunk = api(f"/repos/{repo}/issues/{pr['number']}/events?per_page=100&page={page}")
        events += chunk
        if len(chunk) < 100:
            break
        page += 1
    return planner_label.verdict(changed, main_files, events)


GATES = {
    "privacy": gate_privacy, "never-order": gate_never_order, "workflow-triggers": gate_workflow_triggers,
    "contract-additive": gate_contract_additive, "trace": gate_trace, "planner-label": gate_planner_label,
}


def main(name):
    try:
        problems = GATES[name](event())
    except privacy.NoDenyList as e:
        problems = [str(e)]
    for p in problems:
        print(f"{name}: {p}")
    print(f"{name}: {'FAIL' if problems else 'ok'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
