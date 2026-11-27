from pathlib import Path

from stockpilot import store

from stockpilot.sources import universe

FIXTURES = Path(__file__).parents[1] / "fixtures"


def fetch(url):
    path = FIXTURES / url.rsplit("/", 1)[-1]
    return path.read_bytes() if path.exists() else None


def test_stocks_get_names_isins_and_nse_industries(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert universe.refresh_stocks(db, fetch) == 5
    rows = {r[0]: r[1:] for r in db.execute("select symbol, name, industry, isin from stocks").fetchall()}
    assert rows["SBIN"] == ("State Bank of India", "Financial Services", "INE062A01020")
    assert rows["RUBYMILLS"][1] is None                    # outside the indices: no NSE industry
    assert rows["MHHL"][0].startswith("Mohini")            # SME list
