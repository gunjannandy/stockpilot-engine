"""The NSE API session retries timeouts and connection errors too, priming its cookies again before each retry."""
import json
import urllib.error

import pytest

from stockpilot.sources import nse_api


class FakeOpener:
    """Answers each request from a script: a bytes reply, or an exception to raise."""

    def __init__(self, script):
        self.script, self.urls = list(script), []

    def open(self, request, timeout=None):
        self.urls.append(request.full_url)
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return type("R", (), {"read": lambda self: step})()


@pytest.fixture
def session(monkeypatch):
    monkeypatch.setattr(nse_api.time, "sleep", lambda s: None)
    monkeypatch.setattr(nse_api.time, "time", lambda: 10**9)        # never wait for the 1 s spacing
    return nse_api.Session()


HOME, API = nse_api.HOST + "/", nse_api.HOST + "/api/x"


def test_a_timeout_is_retried_with_fresh_cookies(session):
    session._opener = FakeOpener([b"<html>", TimeoutError("timed out"), b"<html>", json.dumps({"ok": 1}).encode()])
    assert session.fetch_json("/api/x") == {"ok": 1}
    assert session._opener.urls == [HOME, API, HOME, API]       # primed, failed, primed again, answered


def test_a_connection_error_is_retried(session):
    session._opener = FakeOpener([b"", urllib.error.URLError("reset"), b"", b'{"ok": 2}'])
    assert session.fetch_json("/api/x") == {"ok": 2}


def test_an_http_error_and_bad_json_are_still_retried(session):
    err = urllib.error.HTTPError(API, 403, "Forbidden", {}, None)
    session._opener = FakeOpener([b"", err, b"", b"not json", b"", b'{"ok": 3}'])
    assert session.fetch_json("/api/x") == {"ok": 3}


def test_it_gives_up_after_three_tries_with_the_last_error(session):
    session._opener = FakeOpener([b"", TimeoutError("a"), b"", TimeoutError("b"), b"", TimeoutError("c")])
    with pytest.raises(TimeoutError, match="c"):
        session.fetch_json("/api/x")
    assert session._opener.urls == [HOME, API] * 3


def test_a_failing_home_page_does_not_stop_the_priming(session):
    forbidden = urllib.error.HTTPError(HOME, 403, "Forbidden", {}, None)
    session._opener = FakeOpener([forbidden, b'{"ok": 4}'])
    assert session.fetch_json("/api/x") == {"ok": 4}


def test_a_second_call_does_not_prime_again(session):
    session._opener = FakeOpener([b"", b'{"a": 1}', b'{"b": 2}'])
    session.fetch_json("/api/x")
    session.fetch_json("/api/y")
    assert session._opener.urls.count(HOME) == 1
