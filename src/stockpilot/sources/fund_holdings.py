"""Fund holdings for overlap: each fund house's monthly portfolio file (SEBI makes every house publish one) becomes dated
ISIN rows per fund. Public data only. Which of those stocks the owners hold is matched privately on the VM with
`overlap`, a pure function over ISIN sets; nothing here ever sees a holding.

Files are .xlsx (read with the repo's standard-library reader) or .csv; one sheet is one scheme's portfolio. Houses
word their sheets differently, so the reader finds the header row by its ISIN column and the columns by their words,
and takes the scheme name, house and 'as on' date from the lines above it. A sheet that cannot be matched to a fund of
that house is reported, never guessed. Published as `fund_holdings/{fund_id}.json` and `fund_holdings/index.json`."""
import csv
import io
import json
import re
import zipfile
from datetime import date, datetime
from pathlib import Path

from stockpilot.sources import fund_universe as fu
from stockpilot.trades.xlsx import Workbook

# The ten largest fund houses by average AUM, as AMFI names them in the scheme master (decision in docs/status/v2-decisions.md:
# "fund overlap from the 10 biggest houses"). Their file addresses live in config/fund_house_sources.json.
HOUSES = ["SBI Mutual Fund", "ICICI Prudential Mutual Fund", "HDFC Mutual Fund", "Nippon India Mutual Fund",
          "Kotak Mahindra Mutual Fund", "Aditya Birla Sun Life Mutual Fund", "UTI Mutual Fund", "Axis Mutual Fund",
          "Mirae Asset Mutual Fund", "DSP Mutual Fund"]

ISIN = re.compile(r"^IN[A-Z0-9]{9}\d$")
_MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
_DATE_TEXT = re.compile(r"(\d{1,2})(?:st|nd|rd|th)?[\s\-/.]+([A-Za-z]{3,9})[\s\-/.,]+(\d{4})")
_DATE_NUM = re.compile(r"(\d{1,2})[/.\-](\d{1,2})[/.\-](\d{4})")


def _col(i: int) -> str:
    return chr(65 + i)


def _num(text) -> float | None:
    t = re.sub(r"[,%\s]", "", str(text or ""))
    try:
        return float(t)
    except ValueError:
        return None


def _date_in(text: str) -> date | None:
    m = _DATE_TEXT.search(text)
    if m and m[2][:3].lower() in _MONTHS:
        try:
            return date(int(m[3]), _MONTHS[m[2][:3].lower()], int(m[1]))
        except ValueError:
            pass
    m = _DATE_NUM.search(text)
    if m:
        try:
            return date(int(m[3]), int(m[2]), int(m[1]))
        except ValueError:
            pass
    return None


def parse_sheet(rows: list[dict[str, str]]) -> dict | None:
    """One scheme's portfolio from a sheet's rows ({column letter: text}), or None when the sheet has no ISIN column."""
    head = next((i for i, r in enumerate(rows) if any("isin" in str(v).lower() for v in r.values())), None)
    if head is None:
        return None
    cols = {}
    for letter, text in rows[head].items():
        t = str(text).lower()
        if "isin" in t:
            cols["isin"] = letter
        elif "quantity" in t or t.strip() == "qty":
            cols["quantity"] = letter
        elif "% to" in t or "%" in t and "nav" in t:
            cols["pct_nav"] = letter
        elif "market" in t or "fair value" in t or "value" in t:
            cols["value_lakh"] = letter
        elif "name" in t or "instrument" in t or "security" in t:
            cols["name"] = letter
    cols.setdefault("name", "A")
    above = [str(v).strip() for r in rows[:head] for v in r.values() if str(v).strip()]
    as_of = next((d for d in map(_date_in, above) if d), None)
    amc = next((t for t in above if "mutual fund" in t.lower() and len(t) < 80), None)
    title = next((t for t in above if t != amc and not _date_in(t) and not re.search(r"portfolio|statement|as (on|at)", t, re.I)), None)
    out = []
    for r in rows[head + 1:]:
        isin = str(r.get(cols["isin"], "")).strip().upper()
        if not ISIN.match(isin):
            continue
        out.append({"isin": isin, "name": str(r.get(cols["name"], "")).strip(), "quantity": _num(r.get(cols.get("quantity"))),
                    "value_lakh": _num(r.get(cols.get("value_lakh"))), "pct_nav": _num(r.get(cols.get("pct_nav")))})
    return {"title": title, "amc": amc, "as_of": as_of, "rows": out}


def parse_workbook(blob: bytes, filename: str = "") -> list[dict]:
    """Every portfolio in a file: one per sheet that has an ISIN column. An unreadable file (an old .xls, a web page) gives []."""
    if filename.lower().endswith(".csv"):
        sheets = [[{_col(i): v for i, v in enumerate(row) if v.strip()} for row in csv.reader(io.StringIO(blob.decode("utf-8-sig", errors="replace")))]]
    else:
        try:
            wb = Workbook(blob)
            sheets = [wb.rows(name) for name in wb.sheets]
        except (zipfile.BadZipFile, KeyError):
            return []
    return [p for p in map(parse_sheet, sheets) if p]


# ---- matching to funds -------------------------------------------------------------------------------------------

def _norm(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", re.sub(r"\([^)]*\)", " ", text or "").lower()).split())


def _house(name: str | None) -> str:
    return _norm(re.sub(r"mutual fund", "", name or "", flags=re.I))


def match_fund(portfolio: dict, funds: list[dict]) -> dict | None:
    """The fund of the same house whose cleaned name equals the sheet's title; failing that, the one fund whose name starts
    the title (or the other way round). No house on the sheet: any house. Anything unclear is None."""
    title = _norm(fu.clean_name(portfolio.get("title") or ""))
    if not title:
        return None
    house = _house(portfolio.get("amc"))
    pool = [f for f in funds if not house or _house(f["amc"]) == house]
    exact = [f for f in pool if _norm(f["name"]) == title]
    if len(exact) == 1:
        return exact[0]
    near = [f for f in pool if _norm(f["name"]).startswith(title) or title.startswith(_norm(f["name"]))]
    return near[0] if len(near) == 1 and not exact else None


def load_house(fetch, urls: list[str], funds: list[dict]) -> dict:
    """Read a house's files. `fetch(url)` returns bytes or None. Returns matched portfolios (with fund id), the titles that
    matched no fund, and the urls that gave nothing readable."""
    matched, unmatched, failed = [], [], []
    for url in urls:
        blob = fetch(url)
        portfolios = parse_workbook(blob, url) if blob else []
        if not portfolios:
            failed.append(url)
            continue
        for p in portfolios:
            f = match_fund(p, funds)
            if f is None:
                unmatched.append(p["title"] or "(untitled)")
            else:
                matched.append({"fund_id": f["id"], "name": f["name"], "amc": f["amc"], "as_of": p["as_of"], "rows": p["rows"]})
    return {"matched": matched, "unmatched": unmatched, "failed": failed}


# ---- overlap (pure; the owners' real match runs privately) ----------------------------------------------------------

def overlap(rows: list[dict], held_isins: set[str]) -> dict:
    """How much of a fund is stocks the owners hold. `pct_nav`: the fund's own weight in those stocks. Equities are INE ISINs."""
    held = {i.upper() for i in held_isins}
    shared = [{"isin": r["isin"], "name": r["name"], "pct_nav": r["pct_nav"]} for r in rows if r["isin"] in held]
    equities = [r for r in rows if r["isin"].startswith("INE")]
    return {"shared": shared, "n_shared": len(shared), "n_held": len(held),
            "pct_nav": round(sum(s["pct_nav"] or 0 for s in shared), 2),
            "pct_of_fund_stocks": round(100 * sum(r["isin"] in held for r in equities) / len(equities), 1) if equities else 0.0}


# ---- publishing -----------------------------------------------------------------------------------------------------

def _write(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))
    tmp.replace(path)


def publish(houses: dict[str, dict], out: Path, built_at: str) -> dict:
    """Write one file per fund (latest month wins) and an index of what each house gave. Returns the counts."""
    out = Path(out) / "fund_holdings"
    best: dict[str, dict] = {}
    summary = {}
    for house, got in houses.items():
        dates = [m["as_of"] for m in got["matched"] if m["as_of"]]
        summary[house] = {"funds": len(got["matched"]), "as_of": max(dates).isoformat() if dates else None,
                          "failed_files": len(got["failed"])}
        for m in got["matched"]:
            old = best.get(m["fund_id"])
            if old is None or (m["as_of"] or date.min) >= (old["as_of"] or date.min):
                best[m["fund_id"]] = m
    for fid, m in best.items():
        _write(out / f"{fid}.json", {"id": fid, "name": m["name"], "amc": m["amc"], "as_of": m["as_of"].isoformat() if m["as_of"] else None,
                                     "holdings": m["rows"]})
    counts = {"houses_total": len(houses), "houses_loaded": sum(1 for s in summary.values() if s["funds"]), "funds": len(best),
              "unmatched": sum(len(g["unmatched"]) for g in houses.values())}
    _write(out / "index.json", {"built_at": built_at, "houses": summary, "counts": counts})
    return counts


# ---- the public job -------------------------------------------------------------------------------------------------

def main(argv=None):
    """python -m stockpilot.sources.fund_holdings OUT_DIR [SOURCES.json]: the public job's entry point. SOURCES.json maps a
    house (as AMFI names it) to the addresses of its monthly portfolio files; default config/fund_house_sources.json."""
    import sys
    from stockpilot.sources.http import fetch
    args = argv or sys.argv[1:]
    out = Path(args[0])
    sources = json.loads(Path(args[1] if len(args) > 1 else "config/fund_house_sources.json").read_text())
    if not any(sources.get(h) for h in HOUSES):
        print("No fund house file addresses are configured yet: nothing published.")
        return
    blob = fetch(fu.NAVALL_URL)
    if not blob:
        raise SystemExit("AMFI NAVAll did not answer: nothing published")
    funds = fu.group_funds(fu.parse_navall(blob))
    houses = {h: load_house(lambda u: fetch(u, attempts=3, timeout=120), sources.get(h) or [], funds) for h in HOUSES}
    from datetime import timedelta, timezone
    counts = publish(houses, out, datetime.now(timezone(timedelta(hours=5, minutes=30))).isoformat(timespec="seconds"))
    print(f"fund holdings: {counts['funds']} funds from {counts['houses_loaded']} of {counts['houses_total']} houses; "
          f"{counts['unmatched']} sheets matched no fund.")
    if not counts["houses_loaded"]:
        raise SystemExit("Addresses are configured but no house gave a readable file")


if __name__ == "__main__":
    main()
