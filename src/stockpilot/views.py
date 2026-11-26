"""QUEUE (#115): the D1 views `portfolio`, `smallcase` and `own_record` (the contract's `views` table), written by the VM.

Two writers, one row each, rewritten whole with the contract's `as_of` (the data's date) and `written_at` (IST):
  * `write_from_site` after a build (`ship`): copies the three files the build just wrote, so the view equals the static file.
  * `write_from_store` at the end of a sync: rebuilds them from the store. A sync does not know the day's planned buys or the
    reasoning the build attaches to each holding, so those two come from the row the last build wrote.
`record` has its own writer (the weekly review). Nothing here reads or writes anything outside the private store and D1."""
import json
from datetime import date
from pathlib import Path

from stockpilot.jobrun import IST  # noqa: F401 - the zone every written_at is in

NAMES = ("portfolio", "smallcase", "own_record")


def _upsert(query, name: str, doc: dict, as_of: str, written_at: str) -> None:
    query("insert or replace into views (name, doc, as_of, written_at) values (?, ?, ?, ?)",
          [name, json.dumps(doc, ensure_ascii=False, default=str), as_of, written_at])


def previous(query) -> dict:
    """The documents now in D1, by name."""
    return {r["name"]: json.loads(r["doc"]) for r in query("select name, doc from views where name in ('portfolio', 'smallcase', 'own_record')")}


def _as_of(name: str, doc: dict, today: date) -> str:
    raw = doc.get("snapshot_at") if name == "portfolio" else doc.get("as_of")
    return str(raw)[:10] if raw else today.isoformat()


def write_from_site(site_dir, query, written_at: str, today: date) -> list[str]:
    done = []
    for name in NAMES:
        path = Path(site_dir) / "data" / f"{name}.json"
        if not path.exists():
            continue
        doc = json.loads(path.read_text())
        _upsert(query, name, doc, _as_of(name, doc, today), written_at)
        done.append(name)
    return done


def write_from_store(db, query, today: date, written_at: str, default_budget: float, previous: dict | None = None) -> list[str]:
    from stockpilot import site
    from stockpilot.book import record, smallcase
    before = (previous or {}).get("portfolio") or {}
    names = dict(db.execute("select symbol, name from stocks").fetchall())
    last = dict(db.execute("select symbol, arg_max(close, date) from prices where date <= ? group by symbol", [today]).fetchall())
    made, calls = site._latest_calls(db, today)
    calls_by = {c["symbol"]: c for c in calls}
    planned = before.get("budget", {}).get("planned", 0)
    portfolio = site._portfolio(db, names, calls_by, last, today, site._budget(db, today, default_budget, planned))
    kept = {h["symbol"]: h["reasoning"] for h in before.get("holdings", []) if h.get("reasoning")}
    for h in portfolio["holdings"]:
        if h["symbol"] in kept:
            h["reasoning"] = kept[h["symbol"]]
    docs = {"portfolio": json.loads(json.dumps(portfolio, default=str)),
            "smallcase": json.loads(json.dumps(smallcase.comparison(db, today), default=str)),
            "own_record": json.loads(json.dumps(record.build(db, today), default=str))}
    for name in NAMES:
        _upsert(query, name, docs[name], _as_of(name, docs[name], today), written_at)
    return list(NAMES)
