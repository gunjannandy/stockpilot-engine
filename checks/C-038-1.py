"""C-038-1: the model brief carries no holding or tax field."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "py/tests/analyse"))
from analyse_support import DAY, made_up_inputs  # noqa: E402

from stockpilot.jobs.analyse.brief import PrivateField, build, check_public, render  # noqa: E402


def keys(node):
    if isinstance(node, dict):
        for k, v in node.items():
            yield k
            yield from keys(v)
    elif isinstance(node, list):
        for v in node:
            yield from keys(v)


def test_the_brief_has_no_holding_or_tax_field():
    d = made_up_inputs()
    brief = build("ABC", DAY, facts=d["facts"], history=d["history"], news=d["news"])
    bad = ("hold", "lot", "qty", "quantity", "tax", "cost", "pnl", "account", "budget", "owner")
    assert not [k for k in keys(brief) if any(b in k.lower() for b in bad)]
    check_public(brief)


@pytest.mark.parametrize("key", ["holding", "holdings_qty", "tax_if_sold", "avg_price", "account", "lots", "capital_gain"])
def test_a_private_field_is_refused_wherever_it_sits(key):
    d = made_up_inputs()
    brief = build("ABC", DAY, facts=d["facts"], history=d["history"], news=d["news"])
    brief["facts"][key] = 1
    with pytest.raises(PrivateField):
        render(brief, "p")
