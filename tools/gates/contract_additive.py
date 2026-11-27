"""Contract-additive gate: the PR's generated JSON Schema against production's.

A removed or narrowed field fails. Adding an optional field or widening passes.
"""
import json
from pathlib import Path

DELETE = object()  # for tests: marks a key to remove


def _types(node):
    t = node.get("type")
    return None if t is None else set(t if isinstance(t, list) else [t])


def compare(old, new, path="$"):
    out = []
    if not isinstance(old, dict) or not isinstance(new, dict):
        return out
    ot, nt = _types(old), _types(new)
    if ot is not None:
        if nt is None:
            pass  # unconstrained is wider
        elif not ot <= nt and not (ot == {"integer"} and "number" in nt):
            out.append(f"{path}: type narrowed or changed ({sorted(ot)} to {sorted(nt)})")
    if "enum" in old and "enum" in new:
        gone = [v for v in old["enum"] if v not in new["enum"]]
        if gone:
            out.append(f"{path}: enum lost {len(gone)} value(s)")
    elif "enum" in new and "enum" not in old:
        out.append(f"{path}: enum added")
    for key, lower_is_wider in (("minimum", True), ("minLength", True), ("minItems", True), ("maximum", False), ("maxLength", False), ("maxItems", False)):
        if key in new and (key not in old or (new[key] > old[key] if lower_is_wider else new[key] < old[key])):
            out.append(f"{path}: {key} tightened")
    if "pattern" in new and new.get("pattern") != old.get("pattern"):
        out.append(f"{path}: pattern changed")
    if new.get("additionalProperties") is False and old.get("additionalProperties") is not False:
        out.append(f"{path}: additionalProperties closed")
    extra = set(new.get("required", [])) - set(old.get("required", []))
    if extra:
        out.append(f"{path}: new required field(s) {sorted(extra)}")
    for name, sub in (old.get("properties") or {}).items():
        nsub = (new.get("properties") or {}).get(name)
        if nsub is None:
            out.append(f"{path}.{name}: field removed")
        else:
            out += compare(sub, nsub, f"{path}.{name}")
    for key in ("items", "additionalProperties"):
        if isinstance(old.get(key), dict) and isinstance(new.get(key), dict):
            out += compare(old[key], new[key], f"{path}.{key}")
    for key in ("anyOf", "oneOf", "allOf"):
        if key in old and key in new and len(old[key]) == len(new[key]):
            for i, (a, b) in enumerate(zip(old[key], new[key])):
                out += compare(a, b, f"{path}.{key}[{i}]")
        elif key in old and key in new:
            out.append(f"{path}: {key} changed shape")
    for key in ("$defs", "definitions"):
        for name, sub in (old.get(key) or {}).items():
            nsub = (new.get(key) or {}).get(name)
            out += [f"{path}.{key}.{name}: removed"] if nsub is None else compare(sub, nsub, f"{path}.{key}.{name}")
    return out


def compare_dirs(prod_dir, new_dir):
    """Every schema file production has must still exist and be no narrower. No production schema means nothing to hold."""
    if prod_dir is None or not Path(prod_dir).is_dir():
        return []
    out = []
    for f in sorted(Path(prod_dir).glob("**/*.json")):
        rel = f.relative_to(prod_dir)
        mine = Path(new_dir) / rel
        if not mine.is_file():
            out.append(f"{rel}: schema file removed")
            continue
        out += [f"{rel} {p}" for p in compare(json.loads(f.read_text()), json.loads(mine.read_text()))]
    return out
