"""The Machine: a lease on the store that lets go of the lock while the machine is outside."""
import pytest

from fakes import make_machine
from helpers import hold_lock
from stockpilot import store


def test_the_lease_lets_go_of_the_lock_while_suspended_and_takes_it_back(tmp_path):
    m = make_machine(tmp_path)
    with m.db("daily") as db:
        assert store.holder(m.db_path)["job"] == "daily"
        db.suspend()
        assert store.holder(m.db_path) is None          # a runner call would happen here
        db.execute("select 1")                          # the next use takes the lock again
        assert store.holder(m.db_path)["job"] == "daily"
    assert store.holder(m.db_path) is None


def test_busy_past_the_wait_raises_with_the_holder(tmp_path):
    m = make_machine(tmp_path)
    m.db_path.parent.mkdir(parents=True, exist_ok=True)
    proc = hold_lock(m.db_path, 5)
    try:
        with pytest.raises(store.Busy) as err:
            with m.db("queue", wait_s=0):
                pass
        assert err.value.holder["job"] == "holder-job"
    finally:
        proc.terminate()
        proc.wait()


def test_a_wrapped_fetcher_runs_with_the_lock_free_and_the_next_write_takes_it(tmp_path):
    m = make_machine(tmp_path)
    holders = []

    def fetch(url):
        holders.append(store.holder(m.db_path))
        return b"42"

    with m.db("daily") as db:
        got = int(db.releasing(fetch)("http://x"))
        db.execute("insert into fx values (current_date, 'USDINR', ?)", [got])
        assert store.holder(m.db_path)["job"] == "daily"
    assert holders == [None]
    with m.db("check") as db:
        assert db.execute("select count(*) from fx").fetchone()[0] == 1
