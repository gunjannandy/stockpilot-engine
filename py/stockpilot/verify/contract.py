"""Read `schemas/site-contract.md` and check built site JSON against it (check 6)."""
import json
import re
from pathlib import Path

TYPES = {"str": lambda v: isinstance(v, str), "num": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
         "int": lambda v: isinstance(v, int) and not isinstance(v, bool), "bool": lambda v: isinstance(v, bool),
         "list": lambda v: isinstance(v, list), "obj": lambda v: isinstance(v, dict)}
HEAD = re.compile(r"^## `data/(?P<file>[^`]+)\.json`(?P<partial> \(partial\))?")
MISSING = object()


def parse(path: Path) -> dict[str, list[tuple]]:
    """{file template: [(path, type, nullable, presence)]}"""
    out, cur = {}, None
    for line in Path(path).read_text().splitlines():
        m = HEAD.match(line)
        if m:
            cur = out.setdefault(m["file"], [])
            continue
        if line.startswith("## "):
            cur = None
        if cur is not None and line.startswith("| `"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            cur.append((cells[0].strip("`"), cells[1].rstrip("?"), cells[1].endswith("?"), cells[2]))
    return out


def _walk(node, tokens, trail=""):
    """Yield (where, value) for every place `tokens` reaches; value is MISSING when the last key is absent from a parent that is there."""
    token, rest = tokens[0], tokens[1:]
    is_list = token.endswith("[]")
    name = token[:-2] if is_list else token
    if not isinstance(node, dict):
        return
    if name.startswith("{"):
        children = [(f"{trail}{k}", v) for k, v in node.items()]
    elif name in node:
        children = [(f"{trail}{name}", node[name])]
    else:
        if not rest and not is_list:
            yield f"{trail}{name}", MISSING
        return
    for where, child in children:
        if is_list:
            if not isinstance(child, list):
                if not rest:
                    yield where, child            # the type check reports it
                continue
            for i, item in enumerate(child):
                if rest:
                    yield from _walk(item, rest, f"{where}[{i}].")
                else:
                    yield f"{where}[{i}]", item
        elif rest:
            yield from _walk(child, rest, f"{where}.")
        else:
            yield where, child


def check_file(body, rows, label: str, limit: int = 3) -> list[str]:
    """Problems in one JSON body against its contract rows; at most `limit` per field so one broken field is one line."""
    problems = []
    for path, typ, nullable, presence in rows:
        seen = 0
        for where, value in _walk(body, path.split(".")):
            if value is MISSING:
                if presence == "always":
                    seen += 1
                    if seen <= limit:
                        problems.append(f"{label}: {where} is missing (the contract says it is always there)")
                continue
            if value is None:
                if not nullable:
                    seen += 1
                    if seen <= limit:
                        problems.append(f"{label}: {where} is null (the contract does not allow null)")
                continue
            if not TYPES[typ](value):
                seen += 1
                if seen <= limit:
                    problems.append(f"{label}: {where} is {type(value).__name__}, the contract says {typ}")
        if seen > limit:
            problems.append(f"{label}: {path} broke the contract {seen} times in all")
    return problems


def check_site(site: Path, contract_path: Path, stock_limit: int | None = None) -> tuple[list[str], dict]:
    """Every contract file under `site/data`: (problems, {files, rows checked})."""
    contract = parse(contract_path)
    problems, files = [], 0
    for template, rows in contract.items():
        if "{SYMBOL}" in template:
            folder = Path(site) / "data" / template.split("/")[0]
            paths = sorted(folder.glob("*.json")) if folder.is_dir() else []
            if not paths:
                problems.append(f"{template}: no files in {folder}")
            if stock_limit:
                paths = paths[:stock_limit]
        else:
            paths = [Path(site) / "data" / f"{template}.json"]
        for p in paths:
            files += 1
            if not p.exists():
                problems.append(f"{p.name}: the file is missing")
                continue
            try:
                body = json.loads(p.read_text())
            except ValueError as err:
                problems.append(f"{p.name}: not valid JSON ({err})")
                continue
            problems += check_file(body, rows, f"{p.parent.name}/{p.name}" if "{SYMBOL}" in template else p.name)
    return problems, {"files": files, "contract_files": len(contract)}
