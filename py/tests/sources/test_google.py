import json

import pytest

from stockpilot.sources import google


def make_fetch(responses, seen):
    def fetch(url):
        seen.append(url)
        for op, body in responses.items():
            if f"op={op}" in url:
                return json.dumps(body).encode()
        return None
    return fetch


def test_list_passes_key_op_and_since():
    seen = []
    bridge = google.Bridge("https://script.example/exec", "k" * 40, make_fetch({"list": [{"id": "m1"}]}, seen))
    assert bridge.list(since="2026-11-01T00:00:00Z") == [{"id": "m1"}]
    assert "op=list" in seen[0] and "key=" + "k" * 40 in seen[0] and "since=2026-11-01T00%3A00%3A00Z" in seen[0]


def test_file_and_att_decode_base64():
    import base64
    payload = {"name": "a.pdf", "mime": "application/pdf", "b64": base64.b64encode(b"%PDF-x").decode()}
    bridge = google.Bridge("https://s/exec", "k" * 40, make_fetch({"file": payload, "att": payload}, []))
    assert bridge.file("f1").data == b"%PDF-x"
    got = bridge.att("m1", 2)
    assert got.name == "a.pdf" and got.data == b"%PDF-x"


def test_body_returns_text():
    seen = []
    bridge = google.Bridge("https://s/exec", "k" * 40, make_fetch({"body": {"text": "hello"}}, seen))
    assert bridge.body("m1") == "hello"
    assert "msg=m1" in seen[0]


def test_error_reply_raises():
    bridge = google.Bridge("https://s/exec", "k" * 40, make_fetch({"list": {"error": "denied"}}, []))
    with pytest.raises(google.BridgeError, match="denied"):
        bridge.list()


def test_missing_response_raises():
    bridge = google.Bridge("https://s/exec", "k" * 40, lambda url: None)
    with pytest.raises(google.BridgeError):
        bridge.ping()
