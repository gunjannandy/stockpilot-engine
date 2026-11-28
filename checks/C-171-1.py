"""C-171-1: every code-made sentence template has its Kolkata Bengali form; a template without one fails."""
import re

import pytest

from stockpilot.jobs.forecast import templates as T

BENGALI = re.compile("[ঀ-৿]")


def problems(table: dict) -> list[str]:
    out = []
    for key, t in table.items():
        if not BENGALI.search(t.get("bn", "")):
            out.append(f"{key}: no Bengali")
        elif T.fields(t["en"]) != T.fields(t["bn"]):
            out.append(f"{key}: the two forms use different placeholders")
    return out


def test_every_call_template_has_bengali_with_the_same_placeholders():
    assert problems(T.TEMPLATES) == []


def test_a_template_without_bengali_fails():
    assert problems({"x": {"en": "Hello {a}.", "bn": "Hello {a}."}}) == ["x: no Bengali"]
    assert problems({"x": {"en": "Hello {a}.", "bn": "নমস্কার {b}।"}})


def test_every_rendered_call_sentence_has_bengali():
    from datetime import date

    from stockpilot.jobs.forecast import make_calls
    res = [{"symbol": "A", "exchange": "NSE", "chance_3m": c, "low_3m": 90.0, "likely_3m": 100.0, "high_3m": 120.0}
           for c in (0.2, 0.35, 0.45, 0.54, 0.6, None)]
    rows = make_calls(res, {"horizons": {"63": {"n_test": 500, "hit_rate": 0.5}}}, date(2026, 11, 28), [], {})
    import json
    for r in rows:
        for s in json.loads(r["sentences_json"]):
            assert BENGALI.search(s["bn"]), (r["verdict"], s["key"])


@pytest.mark.parametrize("key", sorted(T.TEMPLATES))
def test_templates_render_without_missing_fields(key):
    vals = {f: "5" for f in T.fields(T.TEMPLATES[key]["en"])}
    assert T.render(key, **vals)["bn"]
