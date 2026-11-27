"""AUDIT #20, #21, #22: the all-time chart file the stock page reads (`chart/<SYMBOL>.json`, contract `chart_history`) is made from the
price history files for every stock in the search index (NSE, NSE SME, BSE, BSE SME), split-adjusted to today's price,
and the deploy ships it. Before this nothing made the file, so every stock page said "no price history"."""
import io
import json
import tarfile
from datetime import date, timedelta
from pathlib import Path

import pytest

from stockpilot.sources import chart_files, history, public_files

ROOT = Path(__file__).resolve().parents[3]
CONTRACT = json.loads((ROOT / "schemas" / "live-contract.json").read_text())


def days(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def store(tmp_path):
    """Three stocks: SPLITCO (a 1:2 split in the middle, the exchange's prev_close is corrected on the ex-date), ANAWIL (NSE SME, short life)
    and BSEONLY (BSE only, scrip code 543210), plus a bond-like stock that is not in the index."""
    st = history.HistoryStore(tmp_path / "h")
    nse, bse = {}, {}
    ds = days(date(2024, 1, 2), 260)
    for i, d in enumerate(ds):
        px = 200.0 + i * 0.5                                    # raw price, before and after the split
        if i >= 130:
            px = px / 2                                         # split ex-date at day 130
        prev = (200.0 + (i - 1) * 0.5) if i else px
        if i == 130:
            prev = prev / 2                                     # the exchange corrects prev_close on the ex-date
        elif i > 130:
            prev = (200.0 + (i - 1) * 0.5) / 2
        nse.setdefault(d, []).append(history._row("NSE", d, "t", symbol="SPLITCO", code=None, series="EQ", isin="INE000S01011", open=px - 1, high=px + 2,
                                                  low=px - 2, close=px, prev_close=prev, volume=1000 + i, trades=10, value=px * 1000))
        if i >= 200:
            nse[d].append(history._row("NSE", d, "t", symbol="ANAWIL", code=None, series="SM", isin="INE1J5V01013", open=50.0, high=52.0, low=49.0,
                                       close=51.0, prev_close=50.5, volume=500, trades=5, value=25500))
        if i >= 100:
            bse.setdefault(d, []).append(history._row("BSE", d, "t", symbol="BSEONLY", code="543210", series="M", isin="INE000B01011", open=10.0, high=11.0,
                                                      low=9.5, close=10.5, prev_close=10.2, volume=70, trades=3, value=735))
        nse[d].append(history._row("NSE", d, "t", symbol="JUNKBOND", code=None, series="EQ", isin="INE000J01011", open=1, high=1, low=1, close=1,
                                   prev_close=1, volume=1, trades=1, value=1))
    st.append_days("NSE", nse)
    st.append_days("BSE", bse)
    return st


INDEX = [{"symbol": "SPLITCO", "exchange": "NSE", "segment": "NSE"}, {"symbol": "ANAWIL", "exchange": "NSE", "segment": "NSE_SME"},
         {"symbol": "BSEONLY", "exchange": "BSE", "segment": "BSE_SME"}]


def build(tmp_path):
    out = tmp_path / "out"
    report = chart_files.build_all(store(tmp_path).dir, INDEX, out)
    return out, report


def load(out, symbol):
    return json.loads((out / "chart" / f"{symbol}.json").read_text())


def test_every_stock_in_the_index_gets_a_file_in_the_contract_shape_and_others_do_not(tmp_path):
    out, report = build(tmp_path)
    assert sorted(p.stem for p in (out / "chart").glob("*.json")) == ["ANAWIL", "BSEONLY", "SPLITCO"]
    shape = CONTRACT["files"]["chart_history"]["shape"]
    for sym in ("SPLITCO", "ANAWIL", "BSEONLY"):
        doc = load(out, sym)
        assert set(doc) == set(shape), sym
        n = len(doc["dates"])
        assert all(len(doc[k]) == n for k in ("open", "high", "low", "close", "volume", "dma50", "dma200")), sym
        assert doc["dates"] == sorted(doc["dates"]) and doc["listed_on"] == doc["dates"][0] and doc["as_of"] == doc["dates"][-1]
    assert report["written"] == 3 and report["missing"] == []


def test_exchange_and_sme_and_bse_stocks_are_covered_and_reported_when_missing(tmp_path):
    out = tmp_path / "out"
    report = chart_files.build_all(store(tmp_path).dir, INDEX + [{"symbol": "NOHISTORY", "exchange": "NSE", "segment": "NSE_SME"}], out)
    assert load(out, "ANAWIL")["exchange"] == "NSE" and len(load(out, "ANAWIL")["dates"]) == 60
    assert load(out, "BSEONLY")["exchange"] == "BSE" and len(load(out, "BSEONLY")["dates"]) == 160
    assert report["missing"] == ["NSE:NOHISTORY"]


def test_prices_are_adjusted_so_a_split_leaves_no_cliff_and_today_is_the_real_price(tmp_path):
    out, _ = build(tmp_path)
    doc = load(out, "SPLITCO")
    close = doc["close"]
    assert doc["adjusted"] is True
    last_raw = (200.0 + 259 * 0.5) / 2
    assert close[-1] == pytest.approx(last_raw, abs=0.01)                       # anchored on the latest real close
    worst = max(abs(close[i] / close[i - 1] - 1) for i in range(1, len(close)))
    assert worst < 0.02                                                         # raw data would show a 50% drop on the ex-date
    assert doc["open"][0] <= doc["high"][0] and doc["low"][0] <= doc["close"][0] <= doc["high"][0]


def test_moving_averages_start_only_when_there_is_enough_history(tmp_path):
    out, _ = build(tmp_path)
    doc = load(out, "SPLITCO")
    assert doc["dma50"][48] is None and doc["dma50"][49] is not None
    assert doc["dma200"][198] is None and doc["dma200"][199] is not None
    short = load(out, "ANAWIL")
    assert all(v is None for v in short["dma200"]) and short["dma50"][48] is None and short["dma50"][49] is not None


def test_a_stock_with_one_day_has_no_chart_file(tmp_path):
    st = history.HistoryStore(tmp_path / "h")
    st.append_days("NSE", {date(2026, 1, 5): [history._row("NSE", date(2026, 1, 5), "t", symbol="NEWCO", code=None, series="EQ", isin="INE000N01011", open=1, high=2,
                                                            low=1, close=2, prev_close=1, volume=1, trades=1, value=1)]})
    out = tmp_path / "out"
    report = chart_files.build_all(st.dir, [{"symbol": "NEWCO", "exchange": "NSE", "segment": "NSE"}], out)
    assert not (out / "chart" / "NEWCO.json").exists() and report["missing"] == ["NSE:NEWCO"]


def test_the_tarball_has_chart_folder_members_and_the_deploy_unpacks_it_into_the_site(tmp_path):
    out, _ = build(tmp_path)
    tar_path = chart_files.pack(out, tmp_path / "chart.tar.gz")
    with tarfile.open(tar_path) as t:
        assert sorted(m.name for m in t.getmembers() if m.isfile()) == ["chart/ANAWIL.json", "chart/BSEONLY.json", "chart/SPLITCO.json"]
    site = tmp_path / "site"
    blobs = {"https://github.com/o/r/releases/download/data-latest/chart.tar.gz": tar_path.read_bytes()}
    done = public_files.fetch_into(site, "o/r", fetch=lambda url: blobs.get(url), mechanical_days=[])
    assert "chart/index.json" in done or (site / "chart" / "SPLITCO.json").exists()
    assert json.loads((site / "chart" / "SPLITCO.json").read_text())["symbol"] == "SPLITCO"


def test_the_stock_facts_tarball_lands_in_the_stock_folder(tmp_path):
    """stock-facts.yml packs `./SYM.json` at the root of its tar (the nightly screen unpacks it flat); the page reads `stock/SYM.json`."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        data = json.dumps({"symbol": "SPLITCO"}).encode()
        info = tarfile.TarInfo("./SPLITCO.json"); info.size = len(data); t.addfile(info, io.BytesIO(data))
    site = tmp_path / "site"
    public_files.fetch_into(site, "o/r", fetch=lambda url: buf.getvalue() if url.endswith("stock-facts.tar.gz") else None, mechanical_days=[])
    assert json.loads((site / "stock" / "SPLITCO.json").read_text()) == {"symbol": "SPLITCO"}
