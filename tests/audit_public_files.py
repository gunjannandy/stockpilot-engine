"""AUDIT: the public files a deploy ships, made by the REAL builders from synthetic inputs: the search index (search_index.build_index),
the all-time chart files (chart_files.build_all over a real history store), the stock facts and the screener table
(screen_table.build_table). The browser check web/tests/e2e-audit.mjs serves them next to the built site.
Usage: uv run python tests/audit_public_files.py <overlay dir>"""
import json
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from chart_files.test_chart_files import days  # noqa: E402

from stockpilot.sources import chart_files, history, screen_table, search_index  # noqa: E402

FIX = Path(__file__).parent / "fixtures"
SME = (b"SYMBOL,NAME_OF_COMPANY,SERIES,DATE_OF_LISTING,PAID_UP_VALUE,ISIN_NUMBER,FACE_VALUE,\n"
       b"ANAWIL,Anand Widgets Limited,SM,10-Aug-26,10,INE1J5V01013,10,\n")
BSE_HEAD = ("TradDt,BizDt,Sgmt,Src,FinInstrmTp,FinInstrmId,ISIN,TckrSymb,SctySrs,XpryDt,FininstrmActlXpryDt,StrkPric,OptnTp,FinInstrmNm,OpnPric\n")
BSE = (BSE_HEAD + "2026-11-20,2026-11-20,CM,BSE,STK,543210,INE000B01011,BSEMICRO,M,,,,,Bse Micro Industries Limited,1\n").encode()


def main(out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    index = search_index.build_index({"nse_main": (FIX / "EQUITY_L.csv").read_bytes(), "nse_sme": SME, "bse_days": [BSE],
                                      "built_at": "2026-11-26T07:00:00+05:30", "min_main": 1})
    (out / "search").mkdir(exist_ok=True)
    (out / "search" / "index.json").write_text(json.dumps(index))
    # history: every stock the dashboard fixture holds, ANAWIL (listed three months ago) and the BSE-only stock
    entries = index["entries"]
    held = {"WIPRO", "TITAN", "ICICIBANK", "M&M", "TCS", "INFY", "SBIN", "RELIANCE", "HDFCBANK"}
    chosen = [e for e in entries if e["symbol"] in held | {"ANAWIL", "BSEMICRO"}]
    st = history.HistoryStore(out.parent / (out.name + "-history"))
    nse, bse = {}, {}
    for e in chosen:
        n = 90 if e["symbol"] == "ANAWIL" else 1500
        start_i = 0
        ds = days(date(2026, 11, 20) - timedelta(days=int(n * 1.5) + 10), n)
        px = 100.0 + (hash(e["symbol"]) % 900)
        for i, d in enumerate(ds):
            c = px * (1 + 0.0004 * i) * (1 + 0.03 * ((i * 7919) % 11 - 5) / 50)
            prev = px * (1 + 0.0004 * (i - 1)) * (1 + 0.03 * (((i - 1) * 7919) % 11 - 5) / 50) if i else c
            row = history._row(e["exchange"], d, "audit", symbol=e["symbol"], code=None if e["exchange"] == "NSE" else "543210", series="SM" if "SME" in e["segment"] else "EQ",
                               isin=e["isin"], open=c * 0.995, high=c * 1.012, low=c * 0.985, close=c, prev_close=prev, volume=10000 + (i * 37) % 5000, trades=100, value=c * 10000)
            (nse if e["exchange"] == "NSE" else bse).setdefault(d, []).append(row)
    st.append_days("NSE", nse)
    if bse:
        st.append_days("BSE", bse)
    report = chart_files.build_all(st.dir, entries, out)
    # facts: the contract's own example, re-labelled per stock (synthetic numbers; real facts come from the weekly public job)
    base = json.loads((Path(__file__).parent / "fixtures" / "live" / "files" / "stock_facts.json").read_text())
    (out / "stock").mkdir(exist_ok=True)
    facts = {}
    for e in chosen:
        doc = {**base, "symbol": e["symbol"], "exchange": e["exchange"], "name": e["name"]}
        (out / "stock" / f"{e['symbol']}.json").write_text(json.dumps(doc))
        facts[(e["symbol"], e["exchange"])] = doc
    (out / "screen").mkdir(exist_ok=True)
    (out / "screen" / "universe.json").write_text(json.dumps(screen_table.build_table(index, facts, {"results": []}, "2026-11-26T23:10:00+05:30")))
    print(json.dumps({"charts": report["written"], "index": index["counts"], "missing_history": len(report["missing"])}))


if __name__ == "__main__":
    main(sys.argv[1])
