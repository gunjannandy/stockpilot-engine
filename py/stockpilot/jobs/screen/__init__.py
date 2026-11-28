"""The screen Job, every night: rank every stock on quality, value, momentum and risk, each a percentile inside its
industry, and say why a stock was left out. Deterministic: the same rows always give the same file, byte for byte.

Public data only. The whole-market run is one content-hashed file per run (dataset `screen`); the pointer and the counts
analysed and passed ride in D1 (the Worth following pane shows them). The file goes to `out/data/` for the release step."""
import hashlib
import json
from pathlib import Path

from stockpilot.analysis.screen import WEIGHTS, _percentiles

KIND = DATASET = "screen"
FACTORS = tuple(WEIGHTS)
MIN_PEERS = 3
MIN_FACTORS = 3


def rank(stocks: list[dict]) -> list[dict]:
    """stocks: [{symbol, exchange, industry, quality, value, momentum, risk}] with each factor a number (higher is better)
    or None. Returns one row per stock in rank order, then the excluded in symbol order. Excluded rows say why."""
    ordered = sorted(stocks, key=lambda s: (s["exchange"], s["symbol"]))
    rows, by_industry = {}, {}
    for s in ordered:
        have = [f for f in FACTORS if s.get(f) is not None]
        why = None
        if not s.get("industry"):
            why = "no industry"
        elif len(have) < MIN_FACTORS:
            why = "too few figures"
        rows[(s["exchange"], s["symbol"])] = {"symbol": s["symbol"], "exchange": s["exchange"], "industry": s.get("industry") or "",
                                              **{f: None for f in FACTORS}, "score": None, "rank": None, "excluded": why}
        if not why:
            by_industry.setdefault(s["industry"], []).append(s)
    for industry, members in by_industry.items():
        if len(members) < MIN_PEERS:
            for s in members:
                rows[(s["exchange"], s["symbol"])]["excluded"] = "too few peers in its industry"
            continue
        pct = {}
        for f in FACTORS:
            vals = {(s["exchange"], s["symbol"]): s[f] for s in members if s.get(f) is not None}
            pct[f] = _percentiles(vals, True) if vals else {}
        for s in members:
            k = (s["exchange"], s["symbol"])
            r = rows[k]
            used = {f: pct[f][k] for f in FACTORS if k in pct[f]}
            for f, v in used.items():
                r[f] = round(v, 4)
            wsum = sum(WEIGHTS[f] for f in used)
            r["score"] = round(sum(WEIGHTS[f] * v for f, v in used.items()) / wsum, 4)
    passed = sorted((r for r in rows.values() if r["score"] is not None), key=lambda r: (-r["score"], r["exchange"], r["symbol"]))
    for i, r in enumerate(passed, 1):
        r["rank"] = i
    left = sorted((r for r in rows.values() if r["score"] is None), key=lambda r: (r["exchange"], r["symbol"]))
    return passed + left


def build_file(rows: list[dict], as_of: str) -> tuple[bytes, dict]:
    """The run's file (canonical JSON), and its published pointer {name, sha256, rows}."""
    body = json.dumps({"as_of": as_of, "rows": rows}, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    sha = hashlib.sha256(body).hexdigest()
    return body, {"name": f"{DATASET}.{sha[:12]}.json", "sha256": sha, "rows": len(rows)}


def summary(rows: list[dict]) -> dict:
    return {"analysed": len(rows), "passed": sum(1 for r in rows if r["excluded"] is None)}


def run(ctx, stocks: list[dict] | None = None, out_dir: Path = Path("out/data")) -> str:
    as_of = str(ctx.range.end)
    stocks = stocks if stocks is not None else _live(ctx)
    rows = rank(stocks)
    body, file = build_file(rows, as_of)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / file["name"]).write_bytes(body)
    s = summary(rows)
    from stockpilot.io.clock import ist_now, ist_text
    out = ctx.client.publish_finish(DATASET, ctx.run_id, source="nse filings, price history", fetched_at=ist_text(ist_now()),
                                    as_of=as_of, file=file, summary=s)
    ctx.progress.line(f"screen: {s['analysed']} analysed, {s['passed']} passed, "
                      f"{'published' if out.get('published') else 'not published'}", "ok" if out.get("published") else "fail")
    if not out.get("published"):
        raise RuntimeError(out.get("reason") or "the screen was not published")
    return f"screened {s['analysed']} stocks, {s['passed']} passed"


def _live(ctx) -> list[dict]:
    """Quality, value, momentum and low risk are the mechanical forecast's rank signals (0 to 1 across stocks); the
    industry is the facts dataset's sector."""
    from stockpilot.jobs.forecast import _live_mechanical
    results, _ = _live_mechanical()
    facts = ctx.client._ok("/api/job-data/facts", None, "GET").get("rows", [])
    sector = {r["symbol"]: r.get("sector") or "" for r in facts}
    out = []
    for r in results:
        sig = r.get("signals") or {}
        out.append({"symbol": r["symbol"], "exchange": r["exchange"], "industry": sector.get(r["symbol"], ""),
                    "quality": sig.get("quality"), "value": sig.get("sector_value"), "momentum": sig.get("momentum"),
                    "risk": sig.get("low_volatility")})
    return out
