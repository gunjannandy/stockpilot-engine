"""The mutual fund universe: AMFI's scheme master (about 16,500 schemes) grouped into about 1,500 funds, each with its
plan and option variants, NAV history since 2006, and TER and AUM. Public market data only; nothing private.

Every scheme lands in exactly one fund. A fund is one portfolio: the same house, category and name once the plan
(Direct/Regular) and option (Growth/IDCW/...) words are taken off. Published as static files (`funds/index.json` for
search, `funds/{id}.json` per fund); shapes: `fund_index` and `fund_facts` in schemas/live-contract.json.

NAV history comes from AMFI's history report in windows of at most 90 days. A window AMFI refuses is halved and retried.
Finished windows are kept in `state`, so a run that stops early (time budget) resumes where it left off. Only each fund's
primary scheme (Direct Growth, else Regular Growth) is charted; the other variants carry their latest NAV only."""
import hashlib
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from stockpilot import fundgroups
from stockpilot.sources.fundcosts import scheme_key
from stockpilot.sources import fund_stats

NAVALL_URL = "https://portal.amfiindia.com/spages/NAVAll.txt"
HISTORY_URL = "https://portal.amfiindia.com/DownloadNAVHistoryReport_Po.aspx?frmdt={start}&todt={end}"
HISTORY_FROM = date(2006, 4, 1)
MAX_WINDOW_DAYS = 90
MIN_WINDOW_DAYS = 7
IST = timezone(timedelta(hours=5, minutes=30))
CATEGORY = re.compile(r"^(?:Open|Close|Interval)[^()]*\((.*)\)\s*$")

_OPTION_WORDS = {"growth", "idcw", "dividend", "payout", "reinvestment", "re", "investment", "bonus", "option", "plan",
                 "monthly", "weekly", "daily", "quarterly", "annual", "yearly", "half", "fortnightly", "of", "and",
                 "income", "distribution", "capital", "withdrawal", "regular", "direct", "reinvest", "periodic",
                 "normal", "institutional"}
_SEGMENT_SPLIT = re.compile(r"\s+-\s+|\s*\(\s*(?=[A-Za-z]+(?:\s|\)))")
_TOKENS = re.compile(r"[a-z]+")


def _is_option_text(text: str) -> bool:
    words = _TOKENS.findall(text.lower())
    return bool(words) and all(w in _OPTION_WORDS for w in words)


def clean_name(name: str) -> str:
    """The scheme name without its plan and option words: segments between ' - ' and bracketed bits made only of them
    are dropped ("Fixed Term Plan - Series 99" stays, "- Direct Plan - Growth Option" goes)."""
    name = " ".join(name.split())
    kept = []
    for seg in re.split(r"\s+-\s+", name):
        seg = re.sub(r"\(([^()]*)\)", lambda m: "" if _is_option_text(m.group(1)) else m.group(0), seg).strip()
        if seg and not _is_option_text(seg) or (seg and not kept):
            kept.append(seg)
    return " - ".join(kept).strip(" -") or name


def plan_of(name: str, plan_text: str = "") -> str:
    return "Direct" if "direct" in f"{plan_text} {name}".lower() else "Regular"


def option_of(name: str, option_text: str = "") -> tuple[str, str]:
    """(option, label): Growth, IDCW or Bonus, and the words as written ('Monthly IDCW')."""
    text = f"{option_text} {name}".lower()
    if re.search(r"idcw|dividend|payout|re-?invest|income distribution", text):
        label = re.search(r"((?:monthly|weekly|daily|quarterly|annual|half[- ]yearly|yearly|fortnightly)\s+)?(idcw|dividend|income distribution[^-()]*)",
                          text)
        return "IDCW", (label.group(0).strip().title().replace("Idcw", "IDCW") if label else "IDCW")
    if "bonus" in text:
        return "Bonus", "Bonus"
    return "Growth", "Growth"


def parse_navall(blob: bytes) -> list[dict]:
    """Every scheme row of NAVAll.txt, with its category and fund house. Rows with 'N.A.' NAV are kept (nav None):
    the scheme still belongs to a fund. Accepts both layouts: 6 columns, or 8 with Plan and Option."""
    category = amc = None
    out = []
    for raw in blob.decode("utf-8", errors="replace").splitlines()[1:]:
        line = raw.strip()
        if not line:
            continue
        if ";" not in line:
            m = CATEGORY.match(line)
            if m:
                category = m.group(1).strip()
            else:
                amc = line
            continue
        p = [x.strip() for x in line.split(";")]
        if len(p) < 6 or not p[0].isdigit():
            continue
        plan_text, option_text = (p[4], p[5]) if len(p) >= 8 else ("", "")
        name = p[3]
        nav_text, day_text = p[-2], p[-1]
        try:
            nav = float(nav_text)
        except ValueError:
            nav = None
        try:
            day = datetime.strptime(day_text, "%d-%b-%Y").date()
        except ValueError:
            day = None
        option, label = option_of(name, option_text)
        isin = next((i for i in (p[1], p[2]) if i and i != "-"), None)
        out.append({"code": int(p[0]), "isin": isin, "name": name, "amc": amc, "category": category,
                    "plan": plan_of(name, plan_text), "option": option, "label": label, "nav": nav, "day": day})
    return out


def _fund_key(s: dict) -> tuple:
    return (s["amc"] or "", s["category"] or "", " ".join(re.sub(r"[^a-z0-9 ]", " ", clean_name(s["name"]).lower()).split()))


def fund_id(fund: dict) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", fund["name"].lower()).strip("-")[:40].strip("-")
    digest = hashlib.sha1("|".join(fund["key"]).encode()).hexdigest()[:6]
    return f"{slug}-{digest}"


def _primary(variants: list[dict]) -> int:
    rank = lambda v: (v["plan"] != "Direct", v["option"] != "Growth", v["code"])
    return min(variants, key=rank)["code"]


def group_funds(schemes: list[dict]) -> list[dict]:
    """Funds, one per (house, category, name without plan and option). Every scheme is in exactly one fund."""
    groups: dict[tuple, list[dict]] = {}
    for s in schemes:
        groups.setdefault(_fund_key(s), []).append(s)
    funds = []
    for key, members in groups.items():
        members = sorted(members, key=lambda s: s["code"])
        names = sorted((clean_name(m["name"]) for m in members), key=lambda n: (-sum(clean_name(m["name"]) == n for m in members), n))
        variants = [{k: m[k] for k in ("code", "isin", "plan", "option", "label", "nav", "day")} for m in members]
        f = {"key": key, "name": names[0], "amc": key[0] or None, "category": key[1] or None, "variants": variants,
             "primary_code": _primary(variants), "ter_regular": None, "ter_direct": None, "aum_cr": None,
             "member_names": [m["name"] for m in members]}
        f["id"] = fund_id(f)
        funds.append(f)
    return sorted(funds, key=lambda f: f["id"])


# ---- costs ---------------------------------------------------------------------------------------------------

def attach_costs(funds: list[dict], ter: dict, aum: dict) -> None:
    """TER (regular, direct) and AUM (crore) from AMFI's name-keyed tables (fundcosts.parse_ter_api, parse_aum_api).
    A fund takes the first of its scheme names, then its own cleaned name, that the table knows."""
    for f in funds:
        keys = list(dict.fromkeys([scheme_key(f["name"])] + [scheme_key(n) for n in f["member_names"]]))
        for k in keys:
            if f["ter_regular"] is None and f["ter_direct"] is None and k in ter:
                f["ter_regular"], f["ter_direct"] = ter[k]
            if f["aum_cr"] is None and k in aum:
                f["aum_cr"] = aum[k]


# ---- NAV history -----------------------------------------------------------------------------------------------

def windows(start: date, end: date, size: int = MAX_WINDOW_DAYS) -> list[tuple[date, date]]:
    out, s = [], start
    while s <= end:
        e = min(s + timedelta(days=size - 1), end)
        out.append((s, e))
        s = e + timedelta(days=1)
    return out


def parse_history(lines, wanted: set[int]):
    """(code, date, nav) for each wanted scheme's data row of AMFI's history report; header, category, house and
    'N.A.' rows are skipped. The report is streamed: only wanted rows are kept."""
    for line in lines:
        p = line.strip().split(";")
        if len(p) < 8 or not p[0].strip().isdigit() or int(p[0]) not in wanted:
            continue
        try:
            yield int(p[0]), datetime.strptime(p[-1].strip(), "%d-%b-%Y").date(), float(p[4])
        except ValueError:
            continue


def _covered(state: dict) -> list[tuple[date, date]]:
    return sorted((date.fromisoformat(a), date.fromisoformat(b)) for a, b in state.get("done", []))


def _gaps(start: date, end: date, covered):
    gaps, cur = [], start
    for a, b in covered:
        if b < cur or a > end:
            continue
        if a > cur:
            gaps.append((cur, a - timedelta(days=1)))
        cur = max(cur, b + timedelta(days=1))
    if cur <= end:
        gaps.append((cur, end))
    return gaps


def load_nav_history(codes: set[int], start: date, end: date, fetch, state: dict, pause: float = 3.0,
                     max_windows: int | None = None) -> dict:
    """Fill `state` (`done`: finished windows, `series`: {code: {iso date: nav}}) for [start, end]. `fetch(a, b)` returns
    the report bytes or None. Windows are at most 90 days; a refused one is halved down to 7 days, then recorded in
    `failed` and left for the next run. Stops after `max_windows` finished fetches. Safe to repeat."""
    series = state.setdefault("series", {})
    done = state.setdefault("done", [])
    state["failed"] = []
    rows = fetched = 0
    todo = [w for gap in _gaps(start, end, _covered(state)) for w in windows(*gap)]
    while todo:
        if max_windows is not None and fetched >= max_windows:
            break
        a, b = todo.pop(0)
        blob = fetch(a, b)
        fetched += 1
        if blob is None:
            if (b - a).days + 1 > MIN_WINDOW_DAYS:
                half = (b - a).days // 2
                todo[:0] = [(a, a + timedelta(days=half)), (a + timedelta(days=half + 1), b)]
            else:
                state["failed"].append([a.isoformat(), b.isoformat()])
            if pause:
                time.sleep(pause)
            continue
        for code, day, nav in parse_history(blob.decode("utf-8", errors="replace").splitlines(), codes):
            series.setdefault(str(code), {})[day.isoformat()] = nav
            rows += 1
        done.append([a.isoformat(), b.isoformat()])
        if pause:
            time.sleep(pause)
    done.sort()
    return {"rows": rows, "fetched": fetched, "remaining": len(todo)}


# ---- coverage and publishing --------------------------------------------------------------------------------------

def _pct(n: int, d: int) -> float:
    return round(100 * n / d, 1) if d else 0.0


def coverage(funds: list[dict], nav_counts: dict, schemes_total: int) -> dict:
    """What the run reached. `nav_counts`: {primary scheme code: rows of history}."""
    n = len(funds)
    mapped = sum(len(f["variants"]) for f in funds)
    with_hist = [f for f in funds if nav_counts.get(f["primary_code"], 0) > 0]
    return {"funds": n, "schemes": schemes_total, "schemes_mapped": mapped,
            "ter_pct": _pct(sum(f["ter_regular"] is not None or f["ter_direct"] is not None for f in funds), n),
            "aum_pct": _pct(sum(f["aum_cr"] is not None for f in funds), n),
            "nav_history": {"funds_with_history": len(with_hist), "pct": _pct(len(with_hist), n),
                            "rows": sum(nav_counts.get(f["primary_code"], 0) for f in funds)}}


def _write(path: Path, doc) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, separators=(",", ":"), ensure_ascii=False))
    tmp.replace(path)


def _iso(d) -> str:
    return d if isinstance(d, str) else d.isoformat()


def publish(funds: list[dict], nav: dict, out: Path, built_at: str, schemes_total: int) -> dict:
    """Write `funds/index.json` and one `funds/{id}.json` per fund under `out`. `nav`: {primary code: [(date, nav)]}.
    Returns the coverage report (also stored in the index)."""
    out = Path(out)
    nav_counts = {c: len(v) for c, v in nav.items()}
    cov = coverage(funds, nav_counts, schemes_total)
    entries = []
    for f in funds:
        prim = next(v for v in f["variants"] if v["code"] == f["primary_code"])
        low = f["name"].lower()
        aliases = list(dict.fromkeys(a for a in (low, (f["amc"] or "").lower().replace(" mutual fund", "") + " " + low) if a.strip()))
        entries.append({"id": f["id"], "name": f["name"], "amc": f["amc"], "category": f["category"],
                        "group": fundgroups.group_of(f["category"], f["name"]), "variants": len(f["variants"]),
                        "primary_code": f["primary_code"], "isin": prim["isin"], "ter_direct": f["ter_direct"],
                        "ter_regular": f["ter_regular"], "aum_cr": f["aum_cr"], "aliases": aliases})
        series = sorted((_iso(d), v) for d, v in nav.get(f["primary_code"], []))
        missing = [w for w, x in (("TER", f["ter_direct"] if f["ter_direct"] is not None else f["ter_regular"]),
                                  ("AUM", f["aum_cr"])) if x is None]
        if not series:
            missing.append("NAV history")
        _write(out / "funds" / f"{f['id']}.json", {
            "id": f["id"], "name": f["name"], "amc": f["amc"], "category": f["category"],
            "as_of": max((v["day"].isoformat() for v in f["variants"] if v["day"]), default=None),
            "variants": [{"code": v["code"], "isin": v["isin"], "plan": v["plan"], "option": v["option"], "label": v["label"],
                          "nav": v["nav"], "nav_date": v["day"].isoformat() if v["day"] else None} for v in f["variants"]],
            "costs": {"ter_regular": f["ter_regular"], "ter_direct": f["ter_direct"], "aum_cr": f["aum_cr"]},
            "nav": {"code": f["primary_code"], "dates": [d for d, _ in series], "nav": [v for _, v in series]},
            "not_available": missing})
    _write(out / "funds" / "index.json", {"built_at": built_at, "entries": entries, "counts": cov})
    _write(out / "funds" / "stats.json", fund_stats.build(entries, nav, built_at))   # T26: returns per fund, category middle lines
    return cov


# ---- the public job ---------------------------------------------------------------------------------------------

def fetch_costs(fetch, today: date) -> tuple[dict, dict]:
    """(ter, aum) name-keyed tables from AMFI's own APIs, as fundcosts reads them, without a database. A house or page that
    does not answer is skipped; this month's TER file falls back to last month's when it is not out yet."""
    from stockpilot.sources import fundcosts as fc, fund_stats
    ids = fc.mf_ids_from(fetch(fc.TER_PAGE))
    ter: dict = {}
    for as_of in (today, today.replace(day=1) - timedelta(days=1)):
        month = f"{as_of.month:02d}-{as_of.year}"
        for mf in ids:
            page, seen = 1, 0
            while True:
                try:
                    doc = json.loads(fetch(fc.TER_API.format(mf=mf, month=month, page=page, size=200)) or b"null")
                except ValueError:
                    doc = None
                if not doc or not doc.get("data"):
                    break
                ter |= fc.parse_ter_api(doc["data"])
                seen += len(doc["data"])
                if seen >= (doc.get("meta") or {}).get("total", seen):
                    break
                page += 1
        if ter:
            break
    aum: dict = {}
    for fy in (1, 2):
        try:
            periods = ((json.loads(fetch(fc.AUM_PERIODS_API.format(fy=fy)) or b"null") or {}).get("data") or {}).get("periods") or []
            if periods:
                doc = json.loads(fetch(fc.AUM_API.format(fy=fy, period=periods[0]["id"])) or b"null")
                aum = fc.parse_aum_api((doc or {}).get("data") or [])
        except (ValueError, AttributeError):
            continue
        if aum:
            break
    return ter, aum


def main(argv=None):
    """python -m stockpilot.sources.fund_universe OUT_DIR STATE.json [MAX_WINDOWS]: the public job's entry point.
    STATE.json holds finished windows and the NAV series between runs (the workflow keeps it on the data-latest release)."""
    import sys
    from stockpilot.sources.http import fetch
    args = argv or sys.argv[1:]
    out, state_path = Path(args[0]), Path(args[1])
    max_windows = int(args[2]) if len(args) > 2 else None
    today = datetime.now(IST).date()
    blob = fetch(NAVALL_URL)
    if not blob:
        raise SystemExit("AMFI NAVAll did not answer: nothing published")
    schemes = parse_navall(blob)
    if len(schemes) < 10000:
        raise SystemExit(f"AMFI scheme master has only {len(schemes)} schemes: nothing published")
    funds = group_funds(schemes)
    ter, aum = fetch_costs(fetch, today)
    attach_costs(funds, ter, aum)
    state = json.loads(state_path.read_text()) if state_path.exists() else {}
    history = lambda a, b: fetch(HISTORY_URL.format(start=a.strftime("%d-%b-%Y"), end=b.strftime("%d-%b-%Y")), attempts=3, timeout=180)
    run = load_nav_history({f["primary_code"] for f in funds}, HISTORY_FROM, today, history, state, max_windows=max_windows)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, separators=(",", ":")))
    nav = {int(c): sorted(s.items()) for c, s in state.get("series", {}).items()}
    cov = publish(funds, nav, out, datetime.now(IST).isoformat(timespec="seconds"), len(schemes))
    print(f"funds: {cov['funds']} from {cov['schemes']} schemes ({cov['schemes_mapped']} mapped). TER {cov['ter_pct']}%, "
          f"AUM {cov['aum_pct']}%. NAV history: {cov['nav_history']['funds_with_history']} funds ({cov['nav_history']['pct']}%), "
          f"{cov['nav_history']['rows']} rows. This run: {run['fetched']} windows, {run['remaining']} left, "
          f"{len(state.get('failed', []))} refused.")


if __name__ == "__main__":
    main()
