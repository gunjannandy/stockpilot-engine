import json
from datetime import datetime

import pytest

from seed_site import AS_OF, TOKENS
from site_export_seed import seed
from stockpilot import site

NOW = datetime(2026, 11, 20, 19, 30)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("export")
    db = seed(root / "sp.duckdb")
    out = root / "site"
    site.build(db, out, today=AS_OF, budget_inr=100000, now=NOW, tokens=TOKENS)
    return out


def load(built, name):
    return json.loads((built / "data" / f"{name}.json").read_text())
