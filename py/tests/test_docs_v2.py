"""T3: README decision rows changed by v2 name a reason and a date; GLOSSARY has the v2 terms."""
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if not (ROOT / "README.md").exists():
    # The public code copy carries no README or docs; this guard only runs where the private docs live.
    pytest.skip("private README.md not in this copy (public engine repo)", allow_module_level=True)
README = (ROOT / "README.md").read_text()
GLOSSARY = (ROOT / "GLOSSARY.md").read_text()

# Rows whose decision v2 changed (area label as it starts the row).
CHANGED_ROWS = [
    "Reader", "Users", "Model", "Evening run", "Store", "Holdings", "Dashboard", "News",
    "Self-heal", "Alerts", "Out of scope", "Approval", "Worth following", "Notifications",
    "Code copy", "VM role", "Delivery",
]
V2_TERMS = ["Job", "Ask", "News buy", "Change feed", "Starting chance"]


def rows():
    out = {}
    for line in README.splitlines():
        if line.startswith("|") and not line.startswith("|---"):
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            if len(cells) == 3:
                out[re.sub(r"\s*\(.*", "", cells[0])] = cells
    return out


def test_every_changed_row_names_reason_and_date():
    table = rows()
    for area in CHANGED_ROWS:
        assert area in table, f"README has no row for {area}"
        area_cell, choice, why = table[area]
        assert why, f"{area}: no reason"
        assert re.search(r"2026-11-25", area_cell + choice + why), f"{area}: no v2 date"
        assert "v2" in area_cell + choice + why, f"{area}: not marked v2"


def test_glossary_has_v2_terms():
    for term in V2_TERMS:
        assert re.search(rf"^\*\*{re.escape(term)}\*\*:", GLOSSARY, re.M), f"GLOSSARY lacks {term}"


def test_readme_does_not_contradict_v2_decisions():
    low = README.lower()
    assert "holds no live data" not in low
    assert "static site on cloudflare pages" not in low
    assert "kv queue" not in low and "worker queue" not in low
    assert "ideas tab" not in low or "worth following" in low
    assert "duckdb on the vm" not in low
    assert "owner only approves" in low or "only the owner approves" in low
