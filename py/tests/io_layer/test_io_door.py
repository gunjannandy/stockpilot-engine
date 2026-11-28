import pytest
from mock_contract import MockContract

from stockpilot.heartbeat import beat
from stockpilot.io import Door, DoorError, RowInvalid, new_run_id, validate_row
from stockpilot.jobs.ping import run as run_ping

GOOD_ROW = {"id": "r-1", "at": "2026-11-27T10:00:00+05:30", "source": "job"}


def door(**kw):
    mock = MockContract(**kw)
    return Door("https://x.example", "k", transport=mock), mock


def test_a_good_row_passes_and_a_row_that_breaks_the_json_schema_fails():
    validate_row("ping", GOOD_ROW)
    for bad in (
        {**GOOD_ROW, "at": "2026-11-27T10:00:00Z"},  # not IST
        {**GOOD_ROW, "source": "phone"},  # not in the enum
        {"id": "", "at": GOOD_ROW["at"], "source": "job"},  # empty id
        {**GOOD_ROW, "extra": 1},  # extra keys are errors
        {"id": "r-1", "source": "job"},  # missing key
    ):
        with pytest.raises(RowInvalid):
            validate_row("ping", bad)


def test_one_bad_row_stops_the_batch_before_anything_is_sent():
    d, mock = door()
    with pytest.raises(RowInvalid):
        d.write_rows("ping", "run-1", [GOOD_ROW, {**GOOD_ROW, "source": "phone"}])
    assert mock.calls == []


def test_write_rows_sends_the_run_id_with_the_rows():
    d, mock = door()
    assert d.write_rows("ping", "run-1", [GOOD_ROW]) == {"accepted": 1, "held_back": 0}
    assert mock.calls == [("ingest_write", {"dataset": "ping", "run_id": "run-1", "rows": [GOOD_ROW]})]


def test_market_status_is_read_from_the_api():
    d, _ = door()
    assert d.market_status()["is_trading_day"] is True


def test_an_error_status_raises():
    d, _ = door(fail_on="ingest_write")
    with pytest.raises(DoorError):
        d.write_rows("ping", "run-1", [GOOD_ROW])


def test_run_ids_name_the_kind_and_differ():
    assert new_run_id("ping").startswith("ping-") and new_run_id("ping") != new_run_id("ping")


def test_a_lost_heartbeat_returns_false_and_does_not_raise():
    d, _ = door(fail_on="heartbeat_write")
    assert beat(d, "job.ping", ok=True) is False


def test_the_ping_job_begins_writes_one_row_finishes_and_beats():
    d, mock = door()
    run_id = run_ping(d)
    assert [c[0] for c in mock.calls] == ["job_begin", "ingest_write", "job_end", "heartbeat_write"]
    rows = mock.calls[1][1]["rows"]
    assert len(rows) == 1 and rows[0]["source"] == "job"
    assert mock.calls[1][1]["run_id"] == run_id
    assert mock.calls[2][1]["status"] == "done"


def test_a_failing_ping_job_endes_failed_and_still_beats():
    d, mock = door(fail_on="ingest_write")
    with pytest.raises(DoorError):
        run_ping(d)
    assert mock.calls[-2][0] == "job_end" and mock.calls[-2][1]["status"] == "failed"
    assert mock.calls[-1][0] == "heartbeat_write" and mock.calls[-1][1]["ok"] is False
