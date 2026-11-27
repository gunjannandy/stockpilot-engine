"""The search index the page loads once: every NSE, NSE SME, BSE and BSE SME stock (symbol, name, ISIN, exchange,
segment). Public market lists only; nothing private. Shape: `search_index` in schemas/live-contract.json.

NSE: the equity list plus the SME list. BSE has no list file we can fetch, so the union of the last few daily
bhavcopies stands in: a stock that did not trade on one day still shows up from another."""
import csv
import io
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from stockpilot.sources.marketdata import BSE_STOCK_GROUPS, BSE_URL
from stockpilot.sources.universe import EQUITY_L, SME_L

BSE_SME_GROUPS = {"M", "MT", "MS"}
IST = timezone(timedelta(hours=5, minutes=30))
MIN_MAIN = 1500          # NSE lists about 2,000 main-board stocks; far fewer means a bad download


class UniverseTooSmall(RuntimeError):
    """A list came back far smaller than it should: do not overwrite yesterday's good index with it."""


def _rows(blob):
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8-sig")))
    reader.fieldnames = [f.strip() for f in reader.fieldnames or []]
    return list(reader)


def _entry(symbol, exchange, segment, name, isin):
    name = " ".join(name.split())
    aliases = [name.lower().replace(" limited", "").replace(" ltd.", "").replace(" ltd", "").strip()]
    if symbol.lower() not in aliases:
        aliases.append(symbol.lower())
    return {"symbol": symbol, "exchange": exchange, "segment": segment, "name": name, "isin": isin,
            "aliases": list(dict.fromkeys(a for a in aliases if a))}


def build_index(src: dict) -> dict:
    """src: nse_main, nse_sme (CSV bytes), bse_days (list of bhavcopy bytes or None), built_at, optional min_main."""
    found = {}   # (symbol, exchange) -> entry; first sight wins, the lists never disagree on a name for long
    for r in _rows(src["nse_main"]):
        found.setdefault((r["SYMBOL"].strip(), "NSE"),
                         _entry(r["SYMBOL"].strip(), "NSE", "NSE", r["NAME OF COMPANY"], r["ISIN NUMBER"].strip()))
    if len(found) < src.get("min_main", MIN_MAIN):
        raise UniverseTooSmall(f"NSE main list has only {len(found)} stocks")
    for r in _rows(src.get("nse_sme") or b""):
        found[(r["SYMBOL"].strip(), "NSE")] = _entry(
            r["SYMBOL"].strip(), "NSE", "NSE_SME", r["NAME_OF_COMPANY"], r["ISIN_NUMBER"].strip())
    for blob in src.get("bse_days") or []:
        if not blob or b"FinInstrmTp" not in blob[:2000]:      # a missing day answers with an HTML page
            continue
        for r in _rows(blob):
            grp = r["SctySrs"].strip()
            if r["FinInstrmTp"].strip() != "STK" or grp not in BSE_STOCK_GROUPS:
                continue
            sym = r["TckrSymb"].strip()
            found.setdefault((sym, "BSE"), _entry(sym, "BSE", "BSE_SME" if grp in BSE_SME_GROUPS else "BSE",
                                                  r["FinInstrmNm"], r["ISIN"].strip()))
    entries = [found[k] for k in sorted(found)]
    counts = {s: sum(e["segment"] == s for e in entries) for s in ("NSE", "NSE_SME", "BSE", "BSE_SME")}
    counts["total"] = len(entries)
    counts["by_exchange"] = {x: sum(e["exchange"] == x for e in entries) for x in ("NSE", "BSE")}
    return {"built_at": src["built_at"], "entries": entries, "counts": counts}


def run(fetch, out: Path, today: date | None = None, days: int = 7, min_main: int = MIN_MAIN) -> dict:
    """Fetch the lists, build the index, write it to `out` (atomically), return the counts."""
    today = today or datetime.now(IST).date()
    bse_days = [fetch(BSE_URL.format(day=today - timedelta(days=i))) for i in range(days)]
    idx = build_index({"nse_main": fetch(EQUITY_L) or b"", "nse_sme": fetch(SME_L), "bse_days": bse_days,
                       "built_at": datetime.now(IST).isoformat(timespec="seconds"), "min_main": min_main})
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp")
    tmp.write_text(json.dumps(idx, separators=(",", ":"), ensure_ascii=False))
    tmp.replace(out)
    return idx["counts"]


def main(argv=None):
    """python -m stockpilot.sources.search_index OUT.json: the public daily job's entry point."""
    import sys
    from stockpilot.sources.http import fetch
    out = Path((argv or sys.argv[1:] or ["search/index.json"])[0])
    c = run(fetch, out)
    print(f"search index: {c['total']} stocks. NSE {c['NSE']} + SME {c['NSE_SME']} = {c['by_exchange']['NSE']}; "
          f"BSE {c['BSE']} + SME {c['BSE_SME']} = {c['by_exchange']['BSE']}")


if __name__ == "__main__":
    main()
