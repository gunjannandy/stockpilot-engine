"""Kite sync, VM side: read the day's account data from the Worker, store a holdings snapshot, and
reconcile it against lots. The Worker holds the Kite token; this module never sees it."""
import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from stockpilot import journal
from stockpilot.sources.http import HEADERS


MISMATCHES_NAMED = 5


class LoginNeeded(RuntimeError):
    """The Worker has no Kite token today: an owner must press Sync now on the dashboard."""


class Worker:
    """Calls the Worker's /api/vm/* routes with the shared key."""

    def __init__(self, base_url: str, key: str, timeout: int = 30):
        self.base, self.key, self.timeout = base_url.rstrip("/"), key, timeout

    def request(self, method: str, path: str, body: dict | None = None) -> tuple[int, object]:
        data = json.dumps(body).encode() if body is not None else None
        headers = {**HEADERS, "X-SP-Key": self.key, "Accept": "application/json"}
        if data:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.status, json.loads(resp.read() or b"null")
        except urllib.error.HTTPError as err:
            raw = err.read()
            try:
                return err.code, json.loads(raw or b"null")
            except ValueError:
                return err.code, raw.decode(errors="replace")

    def get(self, path: str):
        return self.request("GET", path)

    def post(self, path: str, body: dict):
        return self.request("POST", path, body)


def fetch(worker: Worker) -> dict:
    status, data = worker.get("/api/vm/kite")
    if status == 409:
        raise LoginNeeded("Kite login needed: press Sync now on the dashboard.")
    if status != 200:
        raise RuntimeError(f"Worker /api/vm/kite answered {status}")
    return data


def _snapshot_rows(payload: dict) -> list[tuple]:
    rows = []
    for h in payload.get("holdings") or []:
        qty = float(h.get("quantity") or 0) + float(h.get("t1_quantity") or 0)
        if qty:
            rows.append(("stock", h["tradingsymbol"], h.get("isin"), qty, float(h.get("average_price") or 0)))
    for m in payload.get("mf_holdings") or []:
        qty = float(m.get("quantity") or 0)
        if qty:   # Kite names a fund by its ISIN in tradingsymbol
            rows.append(("mf", m["tradingsymbol"], m["tradingsymbol"], qty, float(m.get("average_price") or 0)))
    return rows


def _key(kind: str, symbol: str, isin: str | None) -> tuple[str, str]:
    return kind, isin or symbol


def _num(x: float) -> str:
    return f"{x:g}"


def reconcile(db, rows: list[tuple]) -> list[str]:
    """Compare the snapshot with open lots. Every mismatch is returned; the Health tab gets one problem for all of
    them, worded like the Holdings table's check ("Not in Kite.", "Kite shows 12.")."""
    lots = db.execute("select kind, symbol, isin, sum(quantity - closed_quantity) from lots "
                      "where kind in ('stock', 'mf') group by all").fetchall()
    if not lots:
        message = "Kite holdings not checked: no lots recorded yet (the baseline tradebook is not loaded)."
        journal.problem(db, "kite", message)
        return [message]
    kite_side = {_key(k, s, i): (s, q) for k, s, i, q, _ in rows}
    lot_side = {}
    for k, s, i, q in lots:
        if q and abs(q) > 1e-6:
            lot_side[_key(k, s, i)] = (s, q)
    found = []          # (symbol, check)
    for key in sorted(set(kite_side) | set(lot_side)):
        ks, ls = kite_side.get(key), lot_side.get(key)
        if ks and not ls:
            found.append((ks[0], "No lots for it."))
        elif ls and not ks:
            found.append((ls[0], "Not in Kite."))
        elif abs(ks[1] - ls[1]) > 1e-6:
            found.append((ks[0], f"Kite shows {_num(ks[1])}."))
    if found:
        named = " ".join(f"{symbol}: {check}" for symbol, check in found[:MISMATCHES_NAMED])
        more = f" And {len(found) - MISMATCHES_NAMED} more." if len(found) > MISMATCHES_NAMED else ""
        journal.problem(db, "kite", f"Kite and the lots differ for {len(found)} holdings: {named}{more}",
                        key="kite-mismatch")
    return [f"{symbol}: {check}" for symbol, check in found]


def sync(db, worker: Worker) -> dict:
    return store_payload(db, fetch(worker))


def store_payload(db, payload: dict) -> dict:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    rows = _snapshot_rows(payload)
    db.execute("begin")
    db.executemany("insert into holdings (snapshot_at, kind, symbol, isin, quantity, avg_price, source) "
                   "values (?, ?, ?, ?, ?, ?, 'kite')", [(now, *r) for r in rows])
    db.execute("insert into kite_syncs values (?, ?, ?, ?, ?)",
               [now, *(json.dumps(payload.get(k)) for k in ("trades", "positions", "margins", "gtts"))])
    db.execute("commit")
    mismatches = reconcile(db, rows)
    return {"holdings": len(rows), "mismatches": len(mismatches)}
