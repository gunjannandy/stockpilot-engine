"""Mutual fund master and daily NAVs from AMFI's NAVAll.txt (all schemes, one file, published nightly)."""
import re
from datetime import datetime

import duckdb

NAVALL_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
CATEGORY = re.compile(r"^(?:Open|Close|Interval)[^()]*\((.*)\)\s*$")


def ingest_navall(db: duckdb.DuckDBPyConnection, fetch) -> int:
    text = fetch(NAVALL_URL).decode("utf-8", errors="replace")
    category = house = None
    funds, navs = [], []
    for line in text.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        if ";" not in line:
            m = CATEGORY.match(line)
            if m:
                category = m.group(1).strip()
            else:
                house = line
            continue
        parts = line.split(";")
        if len(parts) < 8:
            continue
        code, isin_g, isin_r, name, plan, option, nav, day = parts[:8]
        try:
            nav_value, nav_day = float(nav), datetime.strptime(day, "%d-%b-%Y").date()
        except ValueError:
            continue  # "N.A." NAVs and malformed rows
        funds.append((int(code), isin_g if isin_g != "-" else None, isin_r if isin_r != "-" else None,
                      name, plan, option, category, house))
        navs.append((nav_day, int(code), nav_value))
    db.executemany("insert or replace into funds values (?, ?, ?, ?, ?, ?, ?, ?)", funds)
    db.executemany("insert or replace into navs values (?, ?, ?)", navs)
    return len(navs)
