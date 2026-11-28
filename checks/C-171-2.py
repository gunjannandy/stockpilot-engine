"""C-171-2: every facts sentence template has its Kolkata Bengali form."""
import re

from stockpilot.jobs.facts.templates import TEMPLATES, fields, render

BN = re.compile(r"[ঀ-৿]")


def test_every_template_has_bengali_with_the_same_placeholders():
    assert TEMPLATES
    for key, t in TEMPLATES.items():
        assert t["en"].strip() and BN.search(t["bn"]), key
        assert fields(t["en"]) == fields(t["bn"]), key


def test_a_rendered_sentence_carries_both_languages():
    s = render("roe", roe="15")
    assert "15" in s["en"] and "15" not in s["bn"] or BN.search(s["bn"])
    assert BN.search(s["bn"])
