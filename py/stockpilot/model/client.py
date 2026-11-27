"""The one model client: the Claude Code CLI with the setup token, no tools, asked through the Worker's gate.

Every ask goes to `/api/model/claim` first. The Worker answers from its cache (same brief, model and
day: free), refuses past the kind's daily cap ("Next update tomorrow"), or hands out one slot. Only then
does the CLI run, and its answer is stored so a repeat costs nothing. Public model Jobs see public data
only; nothing here reads holdings, tax or feedback.
"""
import hashlib
import os
import subprocess
from collections.abc import Callable
from dataclasses import dataclass

from stockpilot.runtime.client import JobClient

from .kinds import model_for

NEXT_UPDATE_TOMORROW = "Next update tomorrow"
TOKEN_ENV = "CLAUDE_CODE_OAUTH_TOKEN"


class OverDailyCap(RuntimeError):
    """The kind's daily model budget is spent. The pane says "Next update tomorrow"."""

    def __init__(self, kind: str):
        super().__init__(NEXT_UPDATE_TOMORROW)
        self.kind = kind


class NoModelToken(RuntimeError):
    """No setup token in the environment (the protected `models` environment holds it)."""


@dataclass(frozen=True)
class Answer:
    text: str
    cached: bool
    model: str


Runner = Callable[[str, str], str]


def brief_hash(brief: str) -> str:
    return hashlib.sha256(brief.encode()).hexdigest()


def claude_command(model: str) -> list[str]:
    """No tools, one turn, plain text out: the model only judges what is in the brief."""
    return ["claude", "-p", "--model", model, "--output-format", "text", "--tools", "", "--max-turns", "1"]


def run_claude(brief: str, model: str, *, timeout: int = 300, run=subprocess.run, env: dict | None = None) -> str:
    env = dict(os.environ if env is None else env)
    if not env.get(TOKEN_ENV):
        raise NoModelToken(f"{TOKEN_ENV} is not set")
    done = run(claude_command(model), input=brief, capture_output=True, text=True, timeout=timeout, env=env, check=False)
    if done.returncode != 0:
        raise RuntimeError(f"the model call failed ({done.returncode}): {done.stderr.strip()[:300]}")
    text = done.stdout.strip()
    if not text:
        raise RuntimeError("the model answered with nothing")
    return text


def ask(kind: str, brief: str, *, client: JobClient, model: str | None = None, runner: Runner | None = None) -> Answer:
    model = model or model_for(kind)
    digest = brief_hash(brief)
    status, claim = client.post("/api/model/claim", {"kind": kind, "model": model, "brief_hash": digest})
    if status == 429:
        raise OverDailyCap(kind)
    if status >= 300:
        raise RuntimeError(f"the model gate answered {status}: {claim.get('error', '')}")
    if claim.get("cached"):
        return Answer(claim["answer"], True, model)
    text = (runner or run_claude)(brief, model)
    client.post("/api/model/answer", {"kind": kind, "model": model, "brief_hash": digest, "answer": text})
    return Answer(text, False, model)
