"""Settings from config/stockpilot.yaml and secrets from .env, with the environment overriding .env."""
import os
from pathlib import Path

import yaml


class MissingSecrets(RuntimeError):
    """Raised by Config.require; the message names every missing secret and where it comes from."""


class Config:
    def __init__(self, root: Path, settings: dict, env_file: dict):
        self.root = root
        self._settings = settings
        self._env_file = env_file

    def get(self, dotted: str, default=None):
        node = self._settings
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def secret(self, name: str) -> str | None:
        return os.environ.get(name) or self._env_file.get(name) or None

    def require(self, *names: str) -> dict:
        missing = [n for n in names if not self.secret(n)]
        if missing:
            hints = self.get("secrets", {}) or {}
            lines = [f"{n} ({hints[n]})" if n in hints else n for n in missing]
            raise MissingSecrets("Missing secrets in .env: " + ", ".join(lines))
        return {n: self.secret(n) for n in names}


def _read_env(path: Path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def load(root: Path | str = ".") -> Config:
    root = Path(root).resolve()
    yaml_path = root / "config" / "stockpilot.yaml"
    settings = yaml.safe_load(yaml_path.read_text()) if yaml_path.exists() else {}
    return Config(root, settings or {}, _read_env(root / ".env"))
