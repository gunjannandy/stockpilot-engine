"""Workflow-triggers gate: every workflow except ci.yml and promote.yml starts only by workflow_dispatch.

A job that uses the `models` environment (the Claude token) must be guarded to main, and ci.yml may not use it at all.
"""
from pathlib import Path

import yaml

EXEMPT = {"ci.yml", "promote.yml"}
REUSABLE = {"_job.yml"}  # called by the dispatch-only workflows; starts nothing by itself
MAIN_GUARD = "refs/heads/main"


def _triggers(doc):
    on = doc.get("on", doc.get(True))  # PyYAML reads the key `on` as True
    if isinstance(on, str):
        return {on}
    if isinstance(on, list):
        return set(on)
    return set(on or {})


def _env_name(job):
    env = job.get("environment")
    return env.get("name") if isinstance(env, dict) else env


def check(files):
    """`files` maps a workflow file name to its YAML text. Returns a list of problems."""
    problems = []
    for name, text in sorted(files.items()):
        doc = yaml.safe_load(text) or {}
        allowed = {"workflow_call"} if name in REUSABLE else {"workflow_dispatch"}
        if name not in EXEMPT and _triggers(doc) != allowed:
            problems.append(f"{name}: triggers {sorted(_triggers(doc))}; only {' and '.join(sorted(allowed))} is allowed")
        for job_id, job in (doc.get("jobs") or {}).items():
            if _env_name(job) != "models":
                continue
            if name in EXEMPT:
                problems.append(f"{name}: job {job_id} uses the models environment")
            elif MAIN_GUARD not in str(job.get("if", "")):
                problems.append(f"{name}: job {job_id} uses the models environment without an `if` limiting it to main")
    return problems


def check_dir(directory):
    files = {p.name: p.read_text() for p in sorted(Path(directory).glob("*.y*ml"))}
    return check(files)
