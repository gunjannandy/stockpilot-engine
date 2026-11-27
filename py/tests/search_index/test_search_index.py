"""The search index: every NSE, NSE SME, BSE and BSE SME stock, one entry per listing, with counts."""
import json
from datetime import date
from pathlib import Path

import pytest

from stockpilot.sources import search_index as si

FIX = Path(__file__).parents[1] / "fixtures"
SME_CSV = (b"SYMBOL,NAME_OF_COMPANY,SERIES,DATE_OF_LISTING,PAID_UP_VALUE,ISIN_NUMBER,FACE_VALUE,\n"
           b"ANAWIL,Anand Widgets Limited,SM,01-Jan-24,10,INE0AAA01010,10,\n")
BSE_HEAD = ("TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,"
            "OptnTp,FinInstrmNm,OpnPric\n")


def bse(*rows):
    return (BSE_HEAD + "".join(f"2026-11-20,2026-11-20,CM,BSE,{tp},{code},{isin},{sym},{grp},,,,,{nm},1\n"
                               for tp, code, isin, sym, grp, nm in rows)).encode()


def build(**kw):
    args = dict(nse_main=(FIX / "EQUITY_L.csv").read_bytes(), nse_sme=SME_CSV, bse_days=[], built_at="2026-11-25T09:15:00+05:30", min_main=1)
    return si.build_index({**args, **kw})


def by_symbol(idx, symbol, exchange=None):
    return [e for e in idx["entries"] if e["symbol"] == symbol and (exchange is None or e["exchange"] == exchange)]


def test_sme_stock_is_in_the_index_with_its_segment():
    (e,) = by_symbol(build(), "ANAWIL")
    assert (e["exchange"], e["segment"], e["isin"], e["name"]) == ("NSE", "NSE_SME", "INE0AAA01010", "Anand Widgets Limited")
    assert "anand widgets" in e["aliases"]


def test_bse_files_add_main_and_sme_listings_and_skip_debt():
    day = bse(("STK", 500112, "INE062A01020", "SBIN", "A", "STATE BANK OF INDIA"),
              ("STK", 543001, "INE0BBB01011", "BSESME", "M", "BSE SME CO LTD"),
              ("STK", 700001, "INE0CCC07017", "GSEC", "G", "GOVT SEC"))
    idx = build(bse_days=[day])
    assert by_symbol(idx, "BSESME")[0]["segment"] == "BSE_SME"
    assert by_symbol(idx, "SBIN", "BSE")[0]["segment"] == "BSE"
    assert by_symbol(idx, "GSEC") == []


def test_union_of_days_keeps_a_stock_that_traded_on_only_one_day():
    d1 = bse(("STK", 1, "INE0DDD01012", "ONLYMON", "B", "Only Monday Ltd"))
    d2 = bse(("STK", 2, "INE0EEE01013", "ONLYTUE", "B", "Only Tuesday Ltd"))
    idx = build(bse_days=[d1, d2])
    assert by_symbol(idx, "ONLYMON") and by_symbol(idx, "ONLYTUE")


def test_same_company_on_both_exchanges_is_two_entries_and_no_duplicates():
    d = bse(("STK", 500325, "INE002A01018", "RELIANCE", "A", "RELIANCE INDUSTRIES LTD"))
    idx = build(bse_days=[d, d])
    assert {e["exchange"] for e in by_symbol(idx, "RELIANCE")} == {"NSE", "BSE"}
    assert len(by_symbol(idx, "RELIANCE")) == 2


def test_html_page_instead_of_bse_file_is_skipped_not_fatal():
    idx = build(bse_days=[b"<html>not published</html>", None])
    assert idx["counts"]["BSE"] == 0 and idx["counts"]["NSE_SME"] == 1


def test_counts_per_segment_and_exchange_are_reported():
    d = bse(("STK", 1, "INE0DDD01012", "AAA", "B", "A Ltd"), ("STK", 2, "INE0EEE01013", "BBB", "MT", "B Ltd"))
    c = build(bse_days=[d])["counts"]
    assert c["NSE"] == 3 and c["NSE_SME"] == 1 and c["BSE"] == 1 and c["BSE_SME"] == 1
    assert c["total"] == 6 and c["by_exchange"] == {"NSE": 4, "BSE": 2}


def test_published_shape_matches_the_contract_and_is_sorted():
    idx = build()
    assert set(idx) >= {"built_at", "entries", "counts"}
    assert set(idx["entries"][0]) == {"symbol", "exchange", "segment", "name", "isin", "aliases"}
    keys = [(e["symbol"], e["exchange"]) for e in idx["entries"]]
    assert keys == sorted(keys)


def test_empty_nse_main_list_refuses_to_publish():
    with pytest.raises(si.UniverseTooSmall):
        build(nse_main=b"SYMBOL,NAME OF COMPANY, SERIES, DATE OF LISTING, PAID UP VALUE, MARKET LOT, ISIN NUMBER, FACE VALUE\n",
              min_main=1)


def test_run_writes_file_and_report(tmp_path):
    def fetch(url):
        if "EQUITY_L" in url and "SME" not in url:
            return (FIX / "EQUITY_L.csv").read_bytes()
        if "SME_EQUITY_L" in url:
            return SME_CSV
        if "BhavCopy_BSE" in url and "20261120" in url:
            return bse(("STK", 1, "INE0DDD01012", "AAA", "B", "A Ltd"))
        return None
    out = tmp_path / "search" / "index.json"
    report = si.run(fetch, out, today=date(2026, 11, 21), days=3, min_main=1)
    data = json.loads(out.read_text())
    assert report["total"] == len(data["entries"]) == data["counts"]["total"]
    assert "ANAWIL" in {e["symbol"] for e in data["entries"]}
