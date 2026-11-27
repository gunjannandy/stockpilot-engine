"""A merged ticket is closed by the dispatcher, or its dependents wait forever."""
from orch_helpers import *  # noqa: F401,F403
import dispatch

MERGED = {"number": 9, "state": "merged", "ci": "green"}


def closes(*tickets):
    return [c["number"] for c in dispatch.plan(world(list(tickets)))["close"]]


def test_a_merged_ticket_with_every_check_ticked_is_closed():
    assert closes(ticket(1, "A", pr=MERGED)) == [1]


def test_unticked_checks_vm_work_or_an_unmerged_pr_keep_it_open():
    assert closes(ticket(1, "A", pr=MERGED, unticked=["C-9-1"]),
                  ticket(2, "B", pr=MERGED, vm=True),
                  ticket(3, "C", pr={"number": 8, "state": "open", "ci": "green"}),
                  ticket(4, "D")) == []
