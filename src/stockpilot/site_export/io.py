import json
from pathlib import Path


def write_json(out, name: str, body) -> None:
    """`out/data/<name>.json`, compact, keys in the order the code built them (so a second run writes the same bytes)."""
    path = Path(out) / "data" / f"{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(body, default=str, separators=(",", ":")))
