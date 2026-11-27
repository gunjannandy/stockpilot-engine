"""The nightly unit check. Kite says how many units are owned; the lots (built from the owners' documents) must explain
every one of them. A difference is a bug in what we read, never a normal state: each one is named in plain words, becomes
a problem, and the doctor files one GitHub issue for it. US shares are not Kite's, so they are not checked here."""
from dataclasses import dataclass

from stockpilot.book import kinds, positions

TOLERANCE = 0.0005     # a fund unit has three decimals


@dataclass
class Gap:
    isin: str
    symbol: str
    kite: float
    lots: float
    message: str


def _lots(db) -> dict:
    out: dict = {}
    for kind, symbol, isin, qty, currency in db.execute(
            "select kind, symbol, isin, quantity - closed_quantity, coalesce(currency, 'INR') from lots "
            "where quantity - closed_quantity > 1e-9").fetchall():
        if kinds.is_foreign({"kind": kind, "currency": currency}):
            continue
        key = (kinds.canon(kind), isin or symbol)
        old = out.get(key, (symbol, 0.0))
        out[key] = (old[0], old[1] + qty)
    return out


def _message(symbol: str, kite: float, lots: float) -> str:
    u = positions._u
    if not lots:
        return f"{symbol}: Kite shows {u(kite)} units, no document explains any ({u(kite)} unexplained)."
    if not kite:
        return f"{symbol}: the documents show {u(lots)} units, Kite shows none ({u(lots)} unexplained)."
    if kite > lots:
        return f"{symbol}: Kite shows {u(kite)} units, the documents explain {u(lots)} ({u(kite - lots)} unexplained)."
    return f"{symbol}: the documents show {u(lots)} units, Kite shows {u(kite)} ({u(lots - kite)} unexplained)."


def gaps(db) -> list[Gap]:
    """Every holding whose units in the lots differ from Kite's latest snapshot. No snapshot, nothing to check."""
    kite = positions._kite(db)
    if not kite:
        return []
    mine, out = _lots(db), []
    names = {i: s for s, i in db.execute("select symbol, isin from stocks where isin is not null").fetchall()}
    for key in sorted(set(kite) | set(mine), key=str):
        k_sym, k_qty, _ = kite.get(key, (None, 0.0, None))
        l_sym, l_qty = mine.get(key, (None, 0.0))
        if abs(k_qty - l_qty) <= TOLERANCE:
            continue
        symbol = names.get(key[1]) or l_sym or k_sym
        out.append(Gap(key[1], symbol, k_qty, l_qty, _message(symbol, k_qty, l_qty)))
    return out


def record(db) -> list[Gap]:
    """Tonight's check: one problem per holding that differs (Health lists each, plain words), and the problem of a holding
    that agrees again is marked resolved. Returns the gaps."""
    from stockpilot import journal
    found = gaps(db)
    for g in found:
        journal.problem(db, "units", g.message, "error", key=f"units-{g.isin}")
    live = {f"units-{g.isin}" for g in found}
    for ident, key in db.execute("select id, key from problems where job = 'units' and resolution is null").fetchall():
        if key not in live:
            db.execute("update problems set resolution = 'cleared' where id = ?", [ident])
    return found


def findings(db) -> list[dict]:
    """The doctor's shape: ONE fault for all gaps, so a first night with many does not file a pile of issues. The issue
    lists every holding; it clears when none differ."""
    found = gaps(db)
    if not found:
        return []
    lines = "\n".join(f"- {g.message}" for g in found)
    return [{"key": "units-mismatch",
             "summary": f"{len(found)} holding{'s' if len(found) != 1 else ''}: units in the documents differ from Kite",
             "detail": f"Kite decides what is owned; the lots built from the documents must explain every unit. "
                       f"Find which document is missing or misread.\n{lines}"}]
