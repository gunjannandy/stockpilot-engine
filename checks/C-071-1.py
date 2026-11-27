"""C-071-1: the never-order check fails any broker order endpoint in code."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
from gates import never_order  # noqa: E402

# Built at run time so this file passes its own scan.
PLANTED = [
    "kite." + "place_" + "order(variety='regular')",
    "await kite.cancel" + "Order(id)",
    "POST https://api.kite.trade/orders/" + "regular",
    "client.place" + "_gtt(trigger)",
    "kite.convert" + "_position(x)",
    "fetch('/v2/order" + "s/place')",
]


def test_every_planted_endpoint_fails(tmp_path):
    for i, line in enumerate(PLANTED):
        (tmp_path / f"f{i}.py").write_text(f"x = 1\n{line}\n")
    found = never_order.scan_files(tmp_path, [p.name for p in tmp_path.iterdir()])
    assert len(found) == len(PLANTED) and {f.line for f in found} == {2}


def test_read_endpoints_and_plain_words_pass(tmp_path):
    (tmp_path / "a.py").write_text("kite.holdings()\nkite.orders()  # read only\nGET /portfolio/holdings\nthe order of rows\n")
    assert never_order.scan_files(tmp_path, ["a.py"]) == []


def test_the_gate_source_and_this_repo_are_clean():
    root = Path(__file__).resolve().parents[1]
    assert never_order.scan_files(root, never_order.tracked_files(root)) == []
