"""Validate rows and route bodies against the JSON Schemas generated from the contract.

The schemas are build output (`pnpm gen`, git-ignored). A missing schema is an error, never a skip:
a row that nobody can check must not reach the door.
"""

import json
import os
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator


class RowInvalid(ValueError):
    """A row or body that breaks the contract. The message names the dataset and the first breaches."""


def schema_dir() -> Path:
    override = os.environ.get("STOCKPILOT_SCHEMA_DIR")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[3] / "contract" / "generated" / "schemas"


@lru_cache(maxsize=None)
def _validator(name: str, directory: str) -> Draft202012Validator:
    path = Path(directory) / f"{name}.schema.json"
    if not path.is_file():
        raise FileNotFoundError(f"{path} is missing: run `pnpm gen` to build the contract schemas")
    schema = json.loads(path.read_text())
    Draft202012Validator.check_schema(schema)
    return Draft202012Validator(schema)


def check(name: str, value: object) -> None:
    errors = sorted(_validator(name, str(schema_dir())).iter_errors(value), key=lambda e: list(e.path))
    if errors:
        first = "; ".join(f"{'/'.join(map(str, e.path)) or '(row)'}: {e.message}" for e in errors[:3])
        raise RowInvalid(f"{name}: {first}")


def validate_row(dataset: str, row: object) -> None:
    check(f"dataset.{dataset}", row)
