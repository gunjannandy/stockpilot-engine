"""Builders start in the built-in environment: a custom one needs an approval the owner's phone app cannot give."""
from orch_helpers import *  # noqa: F401,F403
import dispatch


def test_builders_start_in_the_default_environment():
    p = dispatch.plan(world([ticket(1, "A")]))
    assert [s["environment"] for s in p["start"]] == ["Default"]
