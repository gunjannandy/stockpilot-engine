"""The nightly mechanical forecast: read the all-time history, fit, test walk-forward, and write the results file the
dashboard reads (mechanical/{date}.json, contract `mechanical_results`) plus a report with the Brier score against two
baselines, calibration bins and the observed range coverage. Public data only; runs on public Actions.

    python -m stockpilot.mechanical.run --history out/history --out out/mechanical-site

Chance is the model's chance of beating the market benchmark by more than the cost hurdle (3 and 6 months). The range is
the stock's own price in rupees at the 10th, 50th and 90th percentile, widened by the adaptive-conformal step so the band
holds about 8 outcomes in 10 in the walk-forward test."""
import argparse
import json
from pathlib import Path

import numpy as np

from stockpilot.mechanical import signals, walkforward as wf

MODEL_VERSION = "mech-v1"
HORIZON_NAMES = {63: "3m", 126: "6m"}


def _num(x, nd=4):
    return None if x is None or not np.isfinite(x) else round(float(x), nd)


def forecast(panel, horizons=(63, 126), extras=None):
    """Returns (results document, report document) for the last day in the panel."""
    t = panel.n_days - 1
    now = wf.rows_at(panel, t, extras)
    sig = signals.compute(panel, t, extras)
    full_history = np.isfinite(panel.close[t])
    skipped = int(full_history.sum()) - (0 if now is None else len(now.stock))
    per_h, report_h = {}, {}
    for h in horizons:
        ds = wf.build_dataset(panel, h)
        rep = wf.walk_forward(panel, h, ds=ds)
        fitted = wf.fit(ds, h)
        if now is None or fitted is None or rep["n_test"] == 0:
            raise RuntimeError(f"not enough history to fit the {h}-day model")
        chance = fitted.chance(now.X, now.bucket)["final"]
        band = fitted.band(now, rep["coverage"]["alpha_final"])
        price = panel.close[t, now.stock][:, None] * (1 + band)
        per_h[h] = (chance, price)
        report_h[str(h)] = rep
    results = []
    for i, s in enumerate(now.stock):
        row = {"symbol": panel.keys[s][1], "exchange": panel.keys[s][0]}
        for h in horizons:
            n = HORIZON_NAMES[h]
            chance, price = per_h[h]
            row[f"chance_{n}"] = round(float(chance[i]), 3)
            row[f"low_{n}"], row[f"likely_{n}"], row[f"high_{n}"] = (round(float(v), 2) for v in price[i])
        row["signals"] = {k: _num(sig[k][s]) for k in signals.NAMES}
        results.append(row)
    n_test = sum(report_h[str(h)]["n_test"] for h in horizons)
    observed = sum(report_h[str(h)]["coverage"]["observed"] * report_h[str(h)]["n_test"] for h in horizons) / n_test
    as_of = str(panel.dates[t])
    doc = {"as_of": as_of, "model_version": MODEL_VERSION, "universe_count": len(results),
           "observed_coverage": round(observed, 3), "results": results}
    report = {"as_of": as_of, "model_version": MODEL_VERSION, "universe_count": len(results),
              "skipped_short_history": skipped, "horizons": report_h,
              "benchmark": "Nifty 50 when given, else the median daily move of the 300 most traded stocks",
              "model_inputs": wf.FEATURES, "information_only": wf.INFO_ONLY,
              "not_trained_on": "quality, sector value, earnings growth: shown, but no point-in-time history exists yet"}
    return doc, report


def report_markdown(rep: dict) -> str:
    out = [f"# Mechanical forecast report, {rep['as_of']} ({rep['model_version']})", "",
           f"Stocks forecast: {rep['universe_count']}. Skipped for short history: {rep['skipped_short_history']}.",
           f"Benchmark: {rep['benchmark']}.",
           f"Model inputs: {', '.join(rep['model_inputs'])}.",
           f"Information only, never in the model: {', '.join(rep['information_only'])}.", ""]
    for h, r in rep["horizons"].items():
        b = r["brier"]
        out += [f"## {h} trading days ({r['n_test']} walk-forward test calls, hit rate {r['hit_rate']:.1%})", "",
                "Brier score, lower is better:", "",
                "| Method | Brier |", "|---|---|",
                f"| Final (blend, Platt calibrated) | {b['final']:.4f} |",
                f"| Base rate alone | {b['base_rate_alone']:.4f} |",
                f"| Always 50% | {b['always_50']:.4f} |",
                f"| Bucket rate only | {b['bucket']:.4f} |",
                f"| Logistic only | {b['logistic']:.4f} |", "",
                "Calibration (predicted vs what happened):", "",
                "| Bin | Predicted | Actual | Calls |", "|---|---|---|---|"]
        out += [f"| {x['bin']} | {x['predicted']:.1%} | {x['actual']:.1%} | {x['n']} |" for x in r["calibration"]]
        c = r["coverage"]
        out += ["", f"Range coverage: the 10-90 band held {c['observed']:.1%} of outcomes (target {c['target']:.0%}, "
                f"{c['n']} calls, adaptive level {c['alpha_final']:.3f}).", "",
                f"Reversal over 1 month, information only: hit rate {r['reversal_check']['low_third_hit_rate']:.1%} for the "
                f"weakest third, {r['reversal_check']['high_third_hit_rate']:.1%} for the strongest third.",
                f"Survivorship: {r['survivorship']}.", ""]
    return "\n".join(out)


def write(out_dir, doc: dict, report: dict) -> None:
    d = Path(out_dir) / "mechanical"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{doc['as_of']}.json").write_text(json.dumps(doc, separators=(",", ":")))
    (d / f"report-{doc['as_of']}.json").write_text(json.dumps(report, indent=1))
    (d / f"report-{doc['as_of']}.md").write_text(report_markdown(report))


def main(argv=None):
    from stockpilot.mechanical.panel import from_history
    from stockpilot.sources.history import open_history
    ap = argparse.ArgumentParser(prog="python -m stockpilot.mechanical.run")
    ap.add_argument("--history", default="out/history", help="directory of prices-*.parquet files (release history-prices)")
    ap.add_argument("--out", default="out/mechanical-site")
    ap.add_argument("--years", type=int, default=9)
    ap.add_argument("--extras", help="optional JSON {'NSE:SYMBOL': {quality, sector_value, earnings_growth, delivery_info}}")
    args = ap.parse_args(argv)
    panel = from_history(open_history(args.history), years=args.years)
    extras = json.loads(Path(args.extras).read_text()) if args.extras else None
    doc, report = forecast(panel, extras=extras)
    write(args.out, doc, report)
    print(report_markdown(report))


if __name__ == "__main__":
    main()
