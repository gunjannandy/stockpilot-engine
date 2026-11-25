"""Test helpers: bulk-insert rows through a DataFrame, because DuckDB inserts one at a time are slow."""
import subprocess
import sys

import pandas as pd

PRICE_COLS = ["date", "symbol", "exchange", "series", "open", "high", "low", "close", "prev_close",
              "volume", "value", "trades"]


def insert_prices(db, rows):
    df = pd.DataFrame(rows, columns=PRICE_COLS)
    db.register("_rows", df)
    db.execute("insert into prices select * from _rows")
    db.unregister("_rows")


HOLD_SCRIPT = """
import sys, time
from stockpilot import store
db = store.open(sys.argv[1], job="holder-job")
print("locked", flush=True)
time.sleep(float(sys.argv[2]))
store.close(db)
"""


def hold_lock(path, seconds):
    proc = subprocess.Popen([sys.executable, "-c", HOLD_SCRIPT, str(path), str(seconds)], stdout=subprocess.PIPE, text=True)
    assert proc.stdout.readline().strip() == "locked"
    return proc


