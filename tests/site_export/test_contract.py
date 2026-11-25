"""`schemas/site-contract.md` is the data contract the UI builds on. It lists every field of the exported files with a type,
how often it is present and a real example; these tests hold it equal to what `sp build-site` writes."""
import json
import re
from pathlib import Path

import pytest

CONTRACT = Path(__file__).resolve().parents[2] / "schemas" / "site-contract.md"
TYPES = {"str": str, "num": (int, float), "int": int, "bool": bool, "list": list, "obj": dict}
HEAD = re.compile(r"^## `data/(?P<file>[^`]+)\.json`(?P<partial> \(partial\))?")


def parse():
    """{file template: {"partial": bool, "rows": [(path, type, nullable, presence, example)]}}"""
    out, cur = {}, None
    for line in CONTRACT.read_text().splitlines():
        m = HEAD.match(line)
        if m:
            cur = out.setdefault(m["file"], {"partial": bool(m["partial"]), "rows": []})
            continue
        if line.startswith("## "):
            cur = None
        if cur is not None and line.startswith("| `"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            path, typ, presence, example = cells[0].strip("`"), cells[1], cells[2], cells[3]
            cur["rows"].append((path, typ.rstrip("?"), typ.endswith("?"), presence, example))
    return out


def walk(value, path=""):
    """Every (path, value) in a JSON document: dict keys joined by dots, lists as `[]`."""
    yield path, value
    if isinstance(value, dict):
        for k, v in value.items():
            yield from walk(v, f"{path}.{k}" if path else k)
    elif isinstance(value, list):
        for v in value:
            yield from walk(v, f"{path}[]")


def pattern(path):
    """A documented path as a regex: `{name}` stands for any one key (a symbol, an index, a category)."""
    return re.compile("^" + re.sub(r"\\\{[a-z_]+\\\}", r"[^.\[\]]+", re.escape(path)) + "$")


def instances(built, template):
    names = [p.relative_to(built / "data").with_suffix("").as_posix() for p in (built / "data").rglob("*.json")]
    stem = template.replace("{SYMBOL}", "[^/]+")
    return [json.loads((built / "data" / f"{n}.json").read_text()) for n in sorted(names) if re.fullmatch(stem, n)]


def test_the_contract_lists_the_files_lane_a_writes():
    files = parse()
    assert {"history/{SYMBOL}", "stock/{SYMBOL}", "indices", "flows", "trades_closed", "calls_outcomes", "today", "calls", "market", "portfolio"} <= set(files)


def test_every_example_is_json_of_the_declared_type():
    for template, spec in parse().items():
        for path, typ, nullable, presence, example in spec["rows"]:
            assert typ in TYPES, (template, path)
            assert presence in ("always", "sometimes"), (template, path)
            value = json.loads(example.strip("`"))
            assert value is None and nullable or isinstance(value, TYPES[typ]), (template, path, example)


@pytest.mark.parametrize("template", ["history/{SYMBOL}", "stock/{SYMBOL}", "indices", "flows", "trades_closed", "calls_outcomes", "today", "calls", "market", "portfolio"])
def test_documented_fields_exist_with_their_type_and_every_field_is_documented(built, template):
    spec = parse()[template]
    docs = [(pattern(p), p, t, n, pr) for p, t, n, pr, _ in spec["rows"]]
    docs_by_path = {p: (rx, t, n, pr) for rx, p, t, n, pr in docs}
    seen = {p: 0 for p in docs_by_path}
    files = instances(built, template)
    assert files, template
    for doc in files:
        here = {}
        for path, value in walk(doc):
            if not path:
                continue
            hits = [p for p, (rx, *_rest) in docs_by_path.items() if rx.match(path)]
            if hits:
                _, typ, nullable, _ = docs_by_path[hits[0]]
                assert (value is None and nullable) or (isinstance(value, TYPES[typ]) and not (typ == "int" and isinstance(value, bool))
                                                        and not (typ == "num" and isinstance(value, bool))), (template, path, value)
                here[hits[0]] = here.get(hits[0], 0) + 1
                seen[hits[0]] += 1
            elif not spec["partial"]:
                pytest.fail(f"{template}: `{path}` is in the output but not in the contract")
        for p, (_, _, _, presence) in docs_by_path.items():
            if presence == "always" and not p.startswith("{") and p not in here and not re.search(r"\[\]", p):
                pytest.fail(f"{template}: `{p}` is promised on every file but missing from one")
    for p, n in seen.items():
        assert n, f"{template}: `{p}` is in the contract but no built file has it"


def test_the_stale_notes_are_gone(built):
    assert "flows_note" not in json.loads((built / "data/market.json").read_text())
    assert "bulk_deals_note" not in json.loads((built / "data/watchlist.json").read_text())
    text = CONTRACT.read_text()
    assert "flows_note" in text and "bulk_deals_note" in text      # the contract says they were removed
