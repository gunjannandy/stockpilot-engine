"""The all-time chart file for every searchable stock: `chart/<SYMBOL>.json`, contract `chart_history` (spec #24 stories 11-16, 106).

Made on public Actions from the price history files (T5), shipped to the site by the deploy-time fetch (`public_files`). Prices are
adjusted for splits and bonuses so there is no cliff on the ex-date and today's candle is the real price: the exchange's own
`prev_close` is already corrected on the ex-date, so close / prev_close is the true daily step, and the adjusted close is anchored on the
latest real close. Volume is left as traded. Public market data only."""
import json
import tarfile
from pathlib import Path

import numpy as np

from stockpilot.sources import history

BATCH = 300              # symbols per read of the history files
MIN_DAYS = 2             # a chart needs a line; a stock with one day has nothing to draw


def _round(a: np.ndarray) -> list:
    return [None if not np.isfinite(x) else round(float(x), 2 if abs(x) >= 1 else 4) for x in a]


def _rolling_mean(close: np.ndarray, window: int) -> list:
    if len(close) < window:
        return [None] * len(close)
    csum = np.cumsum(np.insert(close, 0, 0.0))
    mean = (csum[window:] - csum[:-window]) / window
    return [None] * (window - 1) + _round(mean)


def adjusted(rows: dict) -> dict:
    """rows: arrays (date, open, high, low, close, prev_close, volume) for one stock, oldest first, one row a day."""
    c, p = rows["close"].astype(float), rows["prev_close"].astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        step = np.where(np.isfinite(p) & (p > 0), c / p, np.nan)
        fallback = np.concatenate([[1.0], c[1:] / c[:-1]])     # no prev_close: the last close we hold
    step = np.where(np.isnan(step), fallback, step)
    step[0] = 1.0
    cum = np.cumprod(step)
    factor = (cum / cum[-1]) * c[-1] / c                       # adjusted close / raw close; 1 on the latest day
    return {"open": rows["open"] * factor, "high": rows["high"] * factor, "low": rows["low"] * factor, "close": c * factor}


def _document(symbol: str, exchange: str, rows: dict) -> dict:
    adj = adjusted(rows)
    dates = [str(d) for d in rows["date"].astype("datetime64[D]")]
    return {"symbol": symbol, "exchange": exchange, "listed_on": dates[0], "as_of": dates[-1], "adjusted": True, "dates": dates,
            "open": _round(adj["open"]), "high": _round(adj["high"]), "low": _round(adj["low"]), "close": _round(adj["close"]),
            "volume": [int(v) if np.isfinite(v) else 0 for v in rows["volume"].astype(float)],
            "dma50": _rolling_mean(adj["close"], 50), "dma200": _rolling_mean(adj["close"], 200)}


def build_all(history_dir, index: list[dict], out_dir) -> dict:
    """Write `<out_dir>/chart/<SYMBOL>.json` for every (exchange, symbol) of the search index that has at least two days of history.
    A symbol listed on both exchanges gets the NSE file. Returns {"written": n, "missing": ["NSE:SYMBOL", ...]}."""
    out = Path(out_dir) / "chart"
    out.mkdir(parents=True, exist_ok=True)
    con = history.open_history(history_dir)
    wanted: dict[str, list[str]] = {}
    for e in sorted(index, key=lambda e: (e["exchange"] != "NSE", e["symbol"])):            # NSE first, so it wins a shared symbol
        wanted.setdefault(e["exchange"], []).append(e["symbol"])
    written: set[str] = set()
    got: set[tuple[str, str]] = set()
    for exchange, symbols in wanted.items():
        for i in range(0, len(symbols), BATCH):
            batch = symbols[i:i + BATCH]
            res = con.execute(
                "select coalesce(symbol, code) as sym, date, open, high, low, close, prev_close, volume from prices "
                "where exchange = ? and coalesce(symbol, code) = any(?) and close is not null and close > 0 order by sym, date",
                [exchange, batch]).fetchnumpy()
            sym = res["sym"].astype(str)
            if not len(sym):
                continue
            cuts = np.flatnonzero(sym[1:] != sym[:-1]) + 1
            for lo, hi in zip(np.concatenate([[0], cuts]), np.concatenate([cuts, [len(sym)]])):
                part = {k: np.ma.filled(np.ma.asarray(v[lo:hi], dtype=float), np.nan) if k != "date" else v[lo:hi] for k, v in res.items() if k != "sym"}
                _, keep = np.unique(part["date"][::-1].astype("datetime64[D]"), return_index=True)      # one row a day, the last one read
                keep = np.sort(len(part["date"]) - 1 - keep)
                part = {k: v[keep] for k, v in part.items()}
                name = str(sym[lo])
                if len(part["date"]) < MIN_DAYS:
                    continue
                got.add((exchange, name))
                if name in written:
                    continue
                (out / f"{name}.json").write_text(json.dumps(_document(name, exchange, part), separators=(",", ":")))
                written.add(name)
    missing = sorted(f"{e['exchange']}:{e['symbol']}" for e in index if (e["exchange"], e["symbol"]) not in got)
    return {"written": len(written), "missing": missing}


def pack(out_dir, tar_path) -> Path:
    """`chart.tar.gz` with members `chart/<SYMBOL>.json`, the folder the page reads."""
    tar_path = Path(tar_path)
    with tarfile.open(tar_path, "w:gz") as t:
        for f in sorted((Path(out_dir) / "chart").glob("*.json")):
            t.add(f, arcname=f"chart/{f.name}")
    return tar_path


def main(argv=None):
    """python -m stockpilot.sources.chart_files HISTORY_DIR SEARCH_INDEX.json OUT_DIR : the public job's entry point."""
    import sys
    a = argv or sys.argv[1:]
    index = json.loads(Path(a[1]).read_text())["entries"]
    report = build_all(a[0], index, a[2])
    pack(a[2], Path(a[2]) / "chart.tar.gz")
    print(json.dumps({"written": report["written"], "missing": len(report["missing"]), "universe": len(index)}))
    (Path(a[2]) / "chart-report.json").write_text(json.dumps(report))


if __name__ == "__main__":
    main()
