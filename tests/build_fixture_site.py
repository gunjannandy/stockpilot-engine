"""Build the dashboard from the seeded fixture DB: python tests/build_fixture_site.py <out dir>"""
import sys
import tempfile
from datetime import datetime
from pathlib import Path

from seed_site import AS_OF, TOKENS, seed
from stockpilot import site

if __name__ == "__main__":
    out = Path(sys.argv[1])
    db = seed(Path(tempfile.mkdtemp()) / "sp.duckdb")
    site.build(db, out, today=AS_OF, budget_inr=100000, now=datetime(2026, 11, 20, 19, 30), tokens=TOKENS)
    print(out)
