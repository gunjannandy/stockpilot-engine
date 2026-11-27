"""Fund running costs from AMFI's free disclosures: Total Expense Ratio (TER, % a year) and average assets (AUM).
Both files are keyed by scheme name, so funds are matched by a name with the plan and option words removed.
The URLs live in config (`funds.ter_url`, `funds.aum_url`) because they could not be verified from the build sandbox:
see docs/research/amfi-ter-aum.md."""
import csv
import json
import io
import re
from datetime import date, timedelta

import duckdb

SMALL_AUM_CR = 500
LAKH_PER_CRORE = 100
_NOISE = re.compile(r"\b(direct|regular|plan|growth|option|idcw|dividend|payout|reinvestment|bonus)\b|[^a-z0-9 ]")


class FormatError(ValueError):
    """The file does not have the columns we expect: better to stop than to read the wrong column."""


def scheme_key(name: str) -> str:
    return " ".join(_NOISE.sub(" ", re.sub(r"\(.*?\)", " ", name.lower())).split())


def _number(text) -> float | None:
    try:
        return float(str(text).replace(",", "").replace("%", "").strip())
    except ValueError:
        return None


def _rows(data: bytes):
    text = data.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None) or []
    return [h.strip().lower() for h in header], list(reader)


def _find(header: list[str], *needles: str, avoid: tuple = ()) -> int:
    for i, h in enumerate(header):
        if all(n in h for n in needles) and not any(a in h for a in avoid):
            return i
    raise FormatError(f"no column with {' + '.join(needles)} in header {header}")


def parse_ter(data: bytes) -> dict[str, tuple]:
    """{scheme key: (regular TER, direct TER)}; rows with no readable TER at all are skipped."""
    header, rows = _rows(data)
    name, reg, direct = _find(header, "scheme"), _find(header, "regular"), _find(header, "direct")
    out = {}
    for r in rows:
        if len(r) <= max(name, reg, direct):
            continue
        pair = (_number(r[reg]), _number(r[direct]))
        if pair != (None, None):
            out[scheme_key(r[name])] = pair
    return out


def parse_aum(data: bytes) -> dict[str, float]:
    """{scheme key: average AUM in rupees crore}. AMFI reports in lakh; a header that says crore is taken as crore."""
    header, rows = _rows(data)
    name, aum = _find(header, "scheme"), _find(header, "aum")
    divisor = 1 if "crore" in header[aum] or "cr." in header[aum] else LAKH_PER_CRORE
    out = {}
    for r in rows:
        if len(r) > max(name, aum) and (v := _number(r[aum])) is not None:
            out[scheme_key(r[name])] = v / divisor
    return out


def ingest(db: duckdb.DuckDBPyConnection, as_of: date, ter: bytes | None, aum: bytes | None) -> int:
    """Store one month's files. A missing file leaves what is already stored for that month untouched."""
    terms = parse_ter(ter) if ter else {}
    assets = parse_aum(aum) if aum else {}
    for key in terms.keys() | assets.keys():
        regular, direct = terms.get(key, (None, None))
        db.execute("""insert into fund_costs values (?, ?, ?, ?, ?)
                      on conflict (key, as_of) do update set
                        ter_regular = coalesce(excluded.ter_regular, fund_costs.ter_regular),
                        ter_direct = coalesce(excluded.ter_direct, fund_costs.ter_direct),
                        aum_cr = coalesce(excluded.aum_cr, fund_costs.aum_cr)""",
                   [key, as_of, regular, direct, assets.get(key)])
    return len(terms.keys() | assets.keys())


def lookup(db, name: str, plan: str | None) -> dict | None:
    row = db.execute("select ter_regular, ter_direct, aum_cr from fund_costs where key = ? order by as_of desc limit 1",
                     [scheme_key(name)]).fetchone()
    if not row:
        return None
    regular = (plan or "").lower().startswith("regular")
    return {"ter": row[0] if regular else row[1], "aum_cr": row[2]}


def both_ters(db, name: str) -> tuple | None:
    row = db.execute("select ter_regular, ter_direct from fund_costs where key = ? order by as_of desc limit 1",
                     [scheme_key(name)]).fetchone()
    return row


def is_small(costs: dict | None) -> bool:
    return bool(costs and costs["aum_cr"] is not None and costs["aum_cr"] < SMALL_AUM_CR)


def refresh(db, as_of: date, ter_url: str | None, aum_url: str | None, fetch) -> int:
    """Download whichever files are configured and store them under the month `as_of` falls in."""
    if not (ter_url or aum_url):
        return 0
    files = []
    for url in (ter_url, aum_url):
        body = fetch(url) if url else None
        if url and body is None:
            raise RuntimeError(f"no file at {url}: check funds.ter_url and funds.aum_url in config/stockpilot.yaml")
        files.append(body)
    return ingest(db, as_of.replace(day=1), *files)


# ---- AMFI's own TER API (the page's data source; checked from the VM 2026-11-25) -----------------------------------

TER_API = ("https://www.amfiindia.com/api/populate-te-rdata-revised?MF_ID={mf}&Month={month}&strCat=-1&strType=1"
           "&page={page}&pageSize={size}")
TER_PAGE = "https://www.amfiindia.com/ter-of-mf-schemes"


def parse_ter_api(rows: list[dict]) -> dict[str, tuple]:
    """{scheme key: (regular TER, direct TER)} from API rows. AMFI writes 0.0000 or nothing where a plan has no cost."""
    out = {}
    for r in rows:
        regular, direct = _number(r.get("R_TER")), _number(r.get("D_TER"))
        out[scheme_key(r.get("Scheme_Name") or "")] = (regular or None, direct or None)
    return out


def mf_ids(page_html: str) -> list[int]:
    """Fund-house ids as the TER page lists them."""
    import re
    return sorted({int(i) for i in re.findall(r'mfId\\?":\\?"(\d+)', page_html)})


def refresh_api(db, as_of: date, fetch, mf_ids: list[int] | None = None, page_size: int = 200, _retry: bool = False) -> int:
    """Costs for the month `as_of` falls in, every fund house, every page. A house that does not answer is skipped (the next
    weekly run asks again); the stored costs of the previous month stay until the new month has them."""
    import json
    ids = mf_ids
    if ids is None:
        body = fetch(TER_PAGE)
        ids = mf_ids_from(body)
    month = f"{as_of.month:02d}-{as_of.year}"
    terms: dict[str, tuple] = {}
    for mf in ids:
        page, seen = 1, 0
        while True:
            body = fetch(TER_API.format(mf=mf, month=month, page=page, size=page_size))
            try:
                doc = json.loads(body) if body else None
            except ValueError:
                doc = None
            if not doc or not doc.get("data"):
                break
            terms |= parse_ter_api(doc["data"])
            seen += len(doc["data"])
            if seen >= (doc.get("meta") or {}).get("total", seen):
                break
            page += 1
    if not terms and not _retry:      # a new month's file is not out yet: the last month's costs are close enough
        return refresh_api(db, (as_of.replace(day=1) - timedelta(days=1)), fetch, ids, page_size, _retry=True)
    return ingest_terms(db, as_of.replace(day=1), terms)


def mf_ids_from(body: bytes | None) -> list[int]:
    return mf_ids((body or b"").decode("utf-8", errors="replace"))


def ingest_terms(db, month: date, terms: dict[str, tuple]) -> int:
    for key, (regular, direct) in terms.items():
        db.execute("""insert into fund_costs values (?, ?, ?, ?, null)
                      on conflict (key, as_of) do update set ter_regular = excluded.ter_regular, ter_direct = excluded.ter_direct""",
                   [key, month, regular, direct])
    return len(terms)


# ---- AMFI's scheme-wise average AUM (lane M, verified on the VM 2026-11-25) --------------------------------------------
# The site's own API (amfiindia.com/aum-data/average-aum page): `fyId` is 1 for the current financial year, 2 for the one
# before; the periods call lists its quarters newest first; `MF_ID=0` returns every fund house in one reply (about 2 MB).
# Rows are grouped: [{Mfname, SchemeCat_Desc, schemes: [{SchemeNAVName, AMFI_Code, AverageAumForTheMonth: {...}}]}], in
# rupees lakh. A fund of funds keeps its size in the "FundOfFundsDomestic" key, the others in the "Excluding..." key.

AUM_PERIODS_API = "https://www.amfiindia.com/api/average-aum-schemewise?strType=Categorywise&fyId={fy}&MF_ID=0"
AUM_API = "https://www.amfiindia.com/api/average-aum-schemewise?strType=Categorywise&fyId={fy}&periodId={period}&MF_ID=0"


def parse_aum_api(groups: list[dict]) -> dict[str, float]:
    """{scheme key: average AUM in rupees crore} from AMFI's grouped rows (lakh / 100). A scheme with no readable amount is
    skipped, never stored as zero; the two AUM keys are added (only one is ever filled), and so are the plans and options that
    share one scheme key."""
    out = {}
    for g in groups:
        for sc in g.get("schemes") or []:
            amounts = [_number(v) for v in (sc.get("AverageAumForTheMonth") or {}).values() if v is not None]
            amounts = [a for a in amounts if a is not None]
            name = sc.get("SchemeNAVName")
            if not name or not amounts:
                continue
            # Direct/Regular and Growth/IDCW are one portfolio under one key: the fund's size is all of them added.
            key = scheme_key(str(name))
            out[key] = out.get(key, 0.0) + sum(amounts) / LAKH_PER_CRORE
    return out


def ingest_aum(db, month: date, assets: dict[str, float]) -> int:
    for key, aum in assets.items():
        db.execute("""insert into fund_costs values (?, ?, null, null, ?)
                      on conflict (key, as_of) do update set aum_cr = excluded.aum_cr""", [key, month, aum])
    return len(assets)


def refresh_aum_api(db, as_of: date, fetch, url: str = AUM_API, periods_url: str = AUM_PERIODS_API) -> int:
    """Average AUM of the latest quarter AMFI has published (this financial year, else last), every fund house. Nothing is
    stored when AMFI does not answer. Returns the number of schemes stored."""
    for fy in (1, 2):
        try:
            doc = json.loads(fetch(periods_url.format(fy=fy)) or b"null")
            periods = (doc.get("data") or {}).get("periods") or []
        except (ValueError, AttributeError):
            continue
        if not periods:
            continue
        try:
            doc = json.loads(fetch(url.format(fy=fy, period=periods[0]["id"])) or b"null")
        except ValueError:
            continue
        assets = parse_aum_api(doc.get("data") or []) if isinstance(doc, dict) else {}
        if assets:
            return ingest_aum(db, as_of.replace(day=1), assets)
    return 0
