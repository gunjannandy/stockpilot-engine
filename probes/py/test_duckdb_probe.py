import http.server, threading, os, re, sys, tempfile
import duckdb
import pytest
sys.path.insert(0, os.path.dirname(__file__))
from duckdb_probe import probe

class H(http.server.BaseHTTPRequestHandler):
    root = None
    ranges = 0
    def log_message(self, *a): pass
    def _send(self, head_only):
        if self.path.startswith("/release/"):
            self.send_response(302); self.send_header("Location", "/asset/f.parquet"); self.end_headers(); return
        data = open(H.root, "rb").read()
        m = re.match(r"bytes=(\d+)-(\d*)", self.headers.get("Range", ""))
        if m:
            H.ranges += 1
            a = int(m.group(1)); b = int(m.group(2)) if m.group(2) else len(data) - 1
            b = min(b, len(data) - 1)
            self.send_response(206); self.send_header("Content-Range", f"bytes {a}-{b}/{len(data)}")
            body = data[a:b+1]
        else:
            self.send_response(200); body = data
        self.send_header("Accept-Ranges", "bytes"); self.send_header("Content-Length", str(len(body))); self.end_headers()
        if not head_only: self.wfile.write(body)
    def do_GET(self): self._send(False)
    def do_HEAD(self): self._send(True)

def _httpfs_available():
    try:
        duckdb.connect().sql("INSTALL httpfs; LOAD httpfs")
        return True
    except Exception:
        return False

@pytest.mark.skipif(not _httpfs_available(), reason="httpfs extension cannot be downloaded here (extensions.duckdb.org is blocked in cloud sessions); runs in the public Actions probe")
def test_reads_parquet_through_a_redirect_and_uses_range_requests():
    d = tempfile.mkdtemp(); f = os.path.join(d, "f.parquet")
    duckdb.sql(f"COPY (SELECT i AS day, i*2 AS close FROM range(200000) t(i)) TO '{f}' (FORMAT parquet, ROW_GROUP_SIZE 20000)")
    H.root = f
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    r = probe(f"http://127.0.0.1:{srv.server_address[1]}/release/f.parquet", "SELECT max(close) FROM t WHERE day BETWEEN 190000 AND 190010")
    srv.shutdown()
    assert r["ok"], r
    assert r["value"] == 380020
    assert r["bytes_fetched"] < os.path.getsize(f)  # read part of the file, not all of it
    assert H.ranges > 0
