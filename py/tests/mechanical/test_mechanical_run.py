import json
import math

import numpy as np

from panel_fixture import make_panel
from stockpilot.mechanical import run

ROOT = __import__("pathlib").Path(__file__).resolve().parents[3]
CONTRACT = json.loads((ROOT / "schemas" / "live-contract.json").read_text())["files"]["mechanical_results"]["shape"]


def _doc():
    p = make_panel(n=80, days=1500, seed=11)
    return p, run.forecast(p, horizons=(63, 126))


def test_results_file_has_exactly_the_contract_keys_and_sane_numbers():
    p, (doc, report) = _doc()
    assert set(doc) == set(CONTRACT)
    assert set(doc["results"][0]) == set(CONTRACT["results"][0])
    assert set(doc["results"][0]["signals"]) == set(CONTRACT["results"][0]["signals"])
    assert doc["universe_count"] == len(doc["results"]) > 60
    for r in doc["results"]:
        assert r["exchange"] in ("NSE", "BSE")
        for h in ("3m", "6m"):
            assert 0.15 <= r[f"chance_{h}"] <= 0.85
            assert 0 < r[f"low_{h}"] < r[f"likely_{h}"] < r[f"high_{h}"]
            assert all(not (isinstance(v, float) and math.isnan(v)) for v in r["signals"].values())
    assert doc["as_of"] == str(p.dates[-1])
    assert 0.5 < doc["observed_coverage"] < 1


def test_range_is_wider_for_a_jumpier_stock_and_wider_for_six_months():
    p = make_panel(n=80, days=1500, seed=11)
    doc, _ = run.forecast(p, horizons=(63, 126))
    width = lambda r, h: (r[f"high_{h}"] - r[f"low_{h}"]) / r[f"likely_{h}"]
    assert np.mean([width(r, "6m") > width(r, "3m") for r in doc["results"]]) > 0.9


def test_report_carries_brier_baselines_calibration_and_coverage_for_each_horizon():
    _, (doc, report) = _doc()
    for h in ("63", "126"):
        r = report["horizons"][h]
        assert {"final", "base_rate_alone", "always_50"} <= set(r["brier"])
        assert r["calibration"] and r["coverage"]["observed"] > 0
    md = run.report_markdown(report)
    low = md.lower()
    assert "brier" in low and "always 50%" in low and "coverage" in low and "information only" in low


def test_write_puts_the_dated_results_and_report_files_in_the_out_dir(tmp_path):
    _, (doc, report) = _doc()
    run.write(tmp_path, doc, report)
    assert json.loads((tmp_path / "mechanical" / f"{doc['as_of']}.json").read_text())["model_version"] == run.MODEL_VERSION
    assert (tmp_path / "mechanical" / f"report-{doc['as_of']}.md").exists()


def test_stocks_with_too_little_history_are_counted_not_forecast():
    p = make_panel(n=80, days=1500, seed=11)
    p.close[:1400, 7] = np.nan
    doc, report = run.forecast(p, horizons=(63, 126))
    assert "NSE:S007" not in {f"{r['exchange']}:{r['symbol']}" for r in doc["results"]}
    assert report["skipped_short_history"] >= 1
