"""Per-stock facts (valuation and quality) with no look-ahead. Every value is a `Record` that carries the date it
became public (`available_on`): results on their broadcast day, shareholding on its filing day, yfinance on the day we
fetched it. `as_of(records, day)` drops everything not yet public on `day`, so a number is never used early.
Filings beat yfinance; yfinance only fills gaps. Public market data only; nothing private. Output shape: `stock_facts`
in schemas/live-contract.json (the fundamentals parts; price, volume and events are merged by their own jobs).

Units: sales, profit, ebit, equity, debt, capital_employed in rupees crore; shares in crore."""
import json
import statistics
from dataclasses import dataclass
from datetime import date
from pathlib import Path

PREFERRED = ("nse", "bse")          # filings; anything else (yfinance) only fills gaps
VALUATION_KEYS = ("pe", "pe_sector", "pe_own_5y_median", "pb", "dividend_yield_pct", "market_cap_cr")
QUALITY_KEYS = ("sales_growth_yoy_pct", "profit_growth_yoy_pct", "roe_pct", "roce_pct", "debt_to_equity",
                "promoter_pct", "pledge_pct")
MIN_SECTOR_PEERS = 5


@dataclass(frozen=True)
class Record:
    metric: str
    value: float
    period_end: date
    available_on: date
    source: str


def as_of(records, day: date) -> list[Record]:
    return [r for r in records if r.available_on <= day]


def _latest(records, metric, prefer=True):
    """Newest period of a metric; a filing wins over yfinance, which is used only if no filing has it."""
    rows = [r for r in records if r.metric == metric]
    if prefer:
        filed = [r for r in rows if r.source in PREFERRED]
        rows = filed or rows
    return max(rows, key=lambda r: (r.period_end, r.available_on), default=None)


def _val(records, metric):
    r = _latest(records, metric)
    return r.value if r else None


def _pct(num, den):
    return round(num / den * 100, 1) if num is not None and den and den > 0 else None


def _growth(records, metric):
    """Latest year against the year before it (330 to 400 days apart); None if either is missing or not positive."""
    rows = sorted((r for r in records if r.metric == metric and r.source in PREFERRED),
                  key=lambda r: r.period_end, reverse=True)
    if not rows:
        return None
    new = rows[0]
    old = next((r for r in rows[1:] if 330 <= (new.period_end - r.period_end).days <= 400), None)
    if old is None or old.value <= 0 or new.value <= 0:
        return None
    return round((new.value / old.value - 1) * 100, 1)


def quality(records, day: date) -> dict:
    rec = as_of(records, day)
    equity, debt = _val(rec, "equity"), _val(rec, "debt")
    out = {
        "sales_growth_yoy_pct": _growth(rec, "sales"),
        "profit_growth_yoy_pct": _growth(rec, "profit"),
        "roe_pct": _pct(_val(rec, "profit"), equity),
        "roce_pct": _pct(_val(rec, "ebit"), _val(rec, "capital_employed")),
        "debt_to_equity": round(debt / equity, 2) if debt is not None and equity and equity > 0 else None,
        "promoter_pct": _val(rec, "promoter_pct"),
        "pledge_pct": _val(rec, "pledge_pct"),
    }
    for key in QUALITY_KEYS:                       # gap fill from a direct figure (yfinance), never over a filing
        if out[key] is None:
            out[key] = _val(rec, key)
    return out


def valuation(records, day: date, price: float | None) -> dict:
    rec = as_of(records, day)
    profit, equity, shares = _val(rec, "profit"), _val(rec, "equity"), _val(rec, "shares")
    out = dict.fromkeys(VALUATION_KEYS)
    if price and shares and shares > 0:
        out["market_cap_cr"] = round(price * shares, 1)
        if profit and profit > 0:
            out["pe"] = round(price / (profit / shares), 1)
        if equity and equity > 0:
            out["pb"] = round(price / (equity / shares), 2)
    for key in ("pe", "pb", "dividend_yield_pct", "market_cap_cr"):
        if out[key] is None:
            out[key] = _val(rec, key)
    return out


def _history_years(records, day: date) -> float:
    ends = [r.period_end for r in as_of(records, day) if r.metric in ("sales", "profit") and r.source in PREFERRED]
    return (max(ends) - min(ends)).days / 365.25 + 1 if ends else 0.0


def _sentences(v, q):
    s = []

    def add(key, en, bn):
        s.append({"key": key, "en": en, "bn": bn})
    if v.get("pe") is not None:
        add("pe", f"Priced at {v['pe']:.0f} times a year's profit.", f"এক বছরের লাভের {v['pe']:.0f} গুণ দামে চলছে।")
    if v.get("pe") is not None and v.get("pe_sector") is not None:
        cheap = v["pe"] < v["pe_sector"]
        add("pe_vs_sector", "Cheaper than its sector." if cheap else "Dearer than its sector.",
            "সেক্টরের চেয়ে সস্তা।" if cheap else "সেক্টরের চেয়ে দামি।")
    if q.get("sales_growth_yoy_pct") is not None:
        g = q["sales_growth_yoy_pct"]
        add("sales_growth", f"Sales {'grew' if g >= 0 else 'fell'} {abs(g):.0f}% in the last year.",
            f"গত এক বছরে বিক্রি {abs(g):.0f}% {'বেড়েছে' if g >= 0 else 'কমেছে'}।")
    if q.get("profit_growth_yoy_pct") is not None:
        g = q["profit_growth_yoy_pct"]
        add("profit_growth", f"Profit {'grew' if g >= 0 else 'fell'} {abs(g):.0f}% in the last year.",
            f"গত এক বছরে লাভ {abs(g):.0f}% {'বেড়েছে' if g >= 0 else 'কমেছে'}।")
    if q.get("roe_pct") is not None:
        add("roe", f"It earns {q['roe_pct']:.0f} rupees a year on every 100 of owners' money.",
            f"মালিকদের প্রতি ১০০ টাকায় বছরে {q['roe_pct']:.0f} টাকা আয় করে।")
    if q.get("debt_to_equity") is not None:
        d = q["debt_to_equity"]
        add("debt", "Little or no debt." if d < 0.3 else f"Owes {d:.1f} rupees for every 1 of owners' money.",
            "ঋণ প্রায় নেই।" if d < 0.3 else f"মালিকের প্রতি ১ টাকায় ঋণ {d:.1f} টাকা।")
    if q.get("promoter_pct") is not None:
        add("promoter", f"Promoters own {q['promoter_pct']:.0f}% of the company.",
            f"প্রমোটারদের হাতে কোম্পানির {q['promoter_pct']:.0f}% আছে।")
    if q.get("pledge_pct") is not None:
        p = q["pledge_pct"]
        add("pledge", "Promoters have pledged none of their shares." if p == 0 else f"Promoters have pledged {p:.0f}% of their shares.",
            "প্রমোটাররা শেয়ার বন্ধক রাখেননি।" if p == 0 else f"প্রমোটাররা নিজেদের শেয়ারের {p:.0f}% বন্ধক রেখেছেন।")
    return s


def build_facts(symbol, exchange, name, sector, records, day: date, price: float | None, extra: dict | None = None) -> dict:
    v, q = valuation(records, day, price), quality(records, day)
    na = [k for k, x in {**v, **q}.items() if x is None]
    if _history_years(records, day) < 10:
        na.append("history_10y")
    doc = {"symbol": symbol, "exchange": exchange, "name": name, "sector": sector, "as_of": day.isoformat(),
           "valuation": v, "quality": q, "sentences": _sentences(v, q), "not_available": na}
    doc.update(extra or {})
    return doc


def add_sector_pe(docs: dict[str, dict]) -> None:
    """Fill each stock's `pe_sector` with the median P/E of its sector, when at least five peers have one."""
    by_sector: dict[str, list[float]] = {}
    for d in docs.values():
        if d["valuation"].get("pe") is not None and d.get("sector"):
            by_sector.setdefault(d["sector"], []).append(d["valuation"]["pe"])
    for d in docs.values():
        peers = by_sector.get(d.get("sector"), [])
        if len(peers) >= MIN_SECTOR_PEERS:
            d["valuation"]["pe_sector"] = round(statistics.median(peers), 1)
            d["not_available"] = [k for k in d["not_available"] if k != "pe_sector"]
            d["sentences"] = _sentences(d["valuation"], d["quality"])


def coverage(docs: dict[str, dict], universe: list[str]) -> dict:
    n = len(universe)
    metrics = {}
    for key in ("pe", "pb", "roe_pct", "roce_pct", "debt_to_equity", "promoter_pct", "pledge_pct"):
        count = sum(1 for s in universe if s in docs and {**docs[s]["valuation"], **docs[s]["quality"]}.get(key) is not None)
        metrics[key] = {"count": count, "pct": round(count / n * 100, 1) if n else 0.0}
    return {"universe": n, "with_facts": sum(1 for s in universe if s in docs), "metrics": metrics}


def write_all(docs: dict[str, dict], cov: dict, out: Path) -> None:
    """stock/{SYMBOL}.json per stock plus facts-coverage.json, each written atomically."""
    out = Path(out)
    (out / "stock").mkdir(parents=True, exist_ok=True)
    for sym, d in docs.items():
        _atomic(out / "stock" / f"{sym}.json", d)
    _atomic(out / "facts-coverage.json", cov)


def _atomic(path: Path, obj) -> None:
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(obj, separators=(",", ":"), ensure_ascii=False))
    tmp.replace(path)
