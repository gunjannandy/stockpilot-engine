"""Judgement runners: send a brief to a model CLI, get decisions back as schema-checked JSON.

analyse() tries each runner in order (config `runners`, e.g. ["claude", "agy"]) and returns the first
valid answer. Each run happens in an empty temporary folder, so the model sees only the brief: never
the repo, the archive or the track record. Claude runs only with the setup token
(CLAUDE_CODE_OAUTH_TOKEN): touching the shared login from a timer can revoke Remote Control.
"""
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = ROOT / "schemas" / "decisions.schema.json"
PROMPTS = ROOT / "prompts"
AGY = os.path.expanduser("~/.local/bin/agy")
MAX_BRIEF_BYTES = 200_000
TIMEOUT = 1800


class RunnerError(RuntimeError):
    pass


def _command(name: str, prompt: str, schema: str, model: str | None) -> list[str]:
    if name == "claude":
        return ["claude", "-p", "--output-format", "json", "--json-schema", schema,
                "--model", model or "sonnet"]
    if name == "agy":
        cmd = [AGY, "-p", prompt, "--output-format", "json", "--json-schema", schema]
        return cmd + (["--model", model] if model else [])
    raise RunnerError(f"unknown runner {name}")


def _parse(name: str, stdout: str) -> dict:
    body = json.loads(stdout)
    if name == "claude" and body.get("is_error"):
        raise RunnerError(f"claude: {body.get('result')}")
    if name == "agy" and body.get("status") != "SUCCESS":
        raise RunnerError(f"agy: {body.get('status')}")
    return body["structured_output"]


def schema_errors(value, schema: dict, path: str = "decisions") -> list[str]:
    """What is wrong with `value` against the JSON schema: types, required keys, bounds. A small checker for the parts of
    JSON Schema the decisions schema uses, so the file stays the one source of truth."""
    kinds = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}

    def is_type(v, t):
        if t == "number":
            return isinstance(v, (int, float)) and not isinstance(v, bool)
        if t == "integer":
            return isinstance(v, int) and not isinstance(v, bool)
        return isinstance(v, kinds[t])
    types = schema.get("type")
    if types and not any(is_type(value, t) for t in ([types] if isinstance(types, str) else types)):
        return [f"{path} is not {types}"]
    errors = []
    if isinstance(value, dict):
        errors += [f"{path}: missing {key}" for key in schema.get("required", []) if key not in value]
        for key, sub in schema.get("properties", {}).items():
            if key in value:
                errors += schema_errors(value[key], sub, f"{path}.{key}")
    elif isinstance(value, list) and "items" in schema:
        for i, v in enumerate(value):
            label = f"{path}[{v.get('symbol', i)}]" if isinstance(v, dict) else f"{path}[{i}]"
            errors += schema_errors(v, schema["items"], label)
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"] or "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path} is {value}, outside {schema.get('minimum')} to {schema.get('maximum')}")
    return errors


def schema_path(role: str) -> Path:
    """The forecaster's roles share the decisions schema; a role with its own file in schemas/ (feedback) uses that."""
    own = ROOT / "schemas" / f"{role}.schema.json"
    return own if own.exists() else SCHEMA


def validate(decisions: dict, schema: Path = SCHEMA) -> dict:
    errors = schema_errors(decisions, json.loads(schema.read_text()))
    if errors:
        raise RunnerError("decisions do not match the schema: " + "; ".join(errors[:5]))
    return decisions


def banned_words() -> list[str]:
    """The words in the first column of prompts/plain-words.md: jargon the owners should never read."""
    out = []
    for line in (PROMPTS / "plain-words.md").read_text().splitlines():
        if line.startswith("- ") and " → " in line:
            out.append(line[2:].split(" → ")[0].strip().lower())
    return out


def jargon_in(text: str) -> list[str]:
    low = (text or "").lower()
    return [w for w in banned_words() if re.search(rf"(?<![\w-]){re.escape(w)}(?![\w-])", low)]


def analyse(brief: dict, role: str, runners: list[str], env: dict | None = None,
            models: dict | None = None, run=subprocess.run) -> dict:
    env = dict(os.environ if env is None else env)
    payload = json.dumps(brief, default=str, separators=(",", ":"))
    if len(payload) > MAX_BRIEF_BYTES:
        raise RunnerError(f"brief is {len(payload)} bytes; the cap is {MAX_BRIEF_BYTES}")
    prompt = (PROMPTS / f"{role}.md").read_text().replace("{{plain-words}}", (PROMPTS / "plain-words.md").read_text()) \
        .replace("{{house-rules}}", (PROMPTS / "house-rules.md").read_text().strip()) + "\n\nBRIEF:\n" + payload
    schema_file = schema_path(role)
    schema = schema_file.read_text()
    failures = []
    for name in runners:
        if name == "claude" and not env.get("CLAUDE_CODE_OAUTH_TOKEN"):
            failures.append({"runner": name, "error": "CLAUDE_CODE_OAUTH_TOKEN is not set"})
            continue
        with tempfile.TemporaryDirectory(prefix="sp-runner-") as empty:
            try:
                # claude reads the prompt on stdin: one argv entry is capped at 128 KB and the brief passes that
                done = run(_command(name, prompt, schema, (models or {}).get(name)), cwd=empty, env=env,
                           capture_output=True, text=True, timeout=TIMEOUT, input=prompt if name == "claude" else None)
                if done.returncode != 0:
                    raise RunnerError(f"{name} exited {done.returncode}: {done.stderr.strip()[:300]}")
                return {"runner": name, "decisions": validate(_parse(name, done.stdout), schema_file), "failures": failures}
            except (RunnerError, json.JSONDecodeError, KeyError, OSError, subprocess.TimeoutExpired) as err:
                failures.append({"runner": name, "error": str(err)[:500]})
    raise RunnerError("every runner failed: " + "; ".join(f"{f['runner']}: {f['error']}" for f in failures))
