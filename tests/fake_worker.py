"""A fake stockpilot Worker for the VM-side tests: serves /api/vm/kite and /api/vm/queue over real HTTP."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

KEY = "vm-test-key"


class FakeWorker:
    def __init__(self, kite=None, queue=None):
        self.kite, self.queue, self.acks, self.seen_keys = kite, queue or [], [], []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body):
                data = json.dumps(body).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _auth(self):
                outer.seen_keys.append(self.headers.get("X-SP-Key"))
                if self.headers.get("X-SP-Key") != KEY:
                    self._send(401, {"error": "no"})
                    return False
                return True

            def do_GET(self):
                if not self._auth():
                    return
                url = urlparse(self.path)
                if url.path == "/api/vm/kite":
                    return self._send(409, {"login_needed": True}) if outer.kite is None else self._send(200, outer.kite)
                if url.path == "/api/vm/queue":
                    after = parse_qs(url.query).get("after", [""])[0]
                    return self._send(200, [i for i in outer.queue if i["id"] > after])
                self._send(404, {})

            def do_POST(self):
                if not self._auth():
                    return
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                if self.path == "/api/vm/queue/ack":
                    outer.acks.append(body)
                    return self._send(200, {"ok": True})
                self._send(404, {})

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
