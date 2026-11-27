"""C-139-1: a removed or narrowed contract field fails against production's schema."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from gates import contract_additive as ca  # noqa: E402

OLD = {
    "type": "object",
    "required": ["a"],
    "properties": {
        "a": {"type": "string", "enum": ["x", "y"], "maxLength": 5},
        "n": {"type": ["number", "null"], "minimum": 0, "maximum": 10},
        "o": {"type": "object", "properties": {"deep": {"type": "integer"}}},
        "l": {"type": "array", "items": {"type": "object", "properties": {"k": {"type": "string"}}}},
    },
}


def copy(**edits):
    import copy as c
    s = c.deepcopy(OLD)
    for path, v in edits.items():
        node = s
        *parents, last = path.split("/")
        for p in parents:
            node = node[p]
        if v is ca.DELETE:
            del node[last]
        else:
            node[last] = v
    return s


def test_a_new_optional_field_and_a_wider_type_pass():
    new = copy()
    new["properties"]["fresh"] = {"type": "string"}
    new["properties"]["a"]["enum"] = ["x", "y", "z"]
    new["properties"]["a"]["maxLength"] = 9
    new["properties"]["n"]["type"] = ["number", "null", "string"]
    new["properties"]["n"]["minimum"] = -5
    assert ca.compare(OLD, new) == []


def test_each_breaking_change_fails():
    breaking = {
        "removed field": copy(**{"properties/a": ca.DELETE}),
        "removed nested field": copy(**{"properties/o/properties/deep": ca.DELETE}),
        "removed array item field": copy(**{"properties/l/items/properties/k": ca.DELETE}),
        "narrowed type": copy(**{"properties/n/type": "number"}),
        "changed type": copy(**{"properties/a/type": "integer"}),
        "removed enum value": copy(**{"properties/a/enum": ["x"]}),
        "raised minimum": copy(**{"properties/n/minimum": 1}),
        "lowered maximum": copy(**{"properties/n/maximum": 5}),
        "shorter maxLength": copy(**{"properties/a/maxLength": 3}),
        "new required": copy(required=["a", "n"]),
        "closed additionalProperties": copy(additionalProperties=False),
    }
    for name, new in breaking.items():
        assert ca.compare(OLD, new), name


def test_compare_dirs_flags_a_deleted_schema_file_and_passes_when_production_has_none(tmp_path):
    import json
    prod, new = tmp_path / "prod", tmp_path / "new"
    prod.mkdir(); new.mkdir()
    (prod / "a.json").write_text(json.dumps(OLD))
    assert ca.compare_dirs(prod, new)
    (new / "a.json").write_text(json.dumps(OLD))
    assert ca.compare_dirs(prod, new) == []
    assert ca.compare_dirs(None, new) == []
