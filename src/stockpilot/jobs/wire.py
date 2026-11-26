"""WIRE: one handler (or one GitHub workflow) for every job kind in `schemas/live-contract.json`.

The one-minute check (`jobs/minute.py`) runs idle most of the time, so this module imports only the standard library and
`jobrun` at the top. Every heavy import (model forms, duckdb, tarfile readers) sits inside the function that needs it.

Kinds and where they run (`coverage()` lists them, and a test walks the contract and fails if one is missing):
  handler   analyse, refresh_call, feedback_read, news_tag, news_rank, weekly_review, backup, sync (sync lives in minute.py)
  workflow  load_stock, news_collect, history_backfill, nightly: `gh workflow run` in the public engine repo

All reads and writes go through `deps.query(sql, params) -> rows` (D1 over HTTP in production, SQLite in tests), the model is
`ctx.model` (a fallback `Chain`; a fake in tests), and every other outside thing is a field of `Deps` so a test can replace it.
Bengali: every progress line, every error and every written row that the contract gives a `_bn` column carries one."""
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

from stockpilot.jobrun import CONTRACT, IST, JobFailed
from stockpilot.modeljson import json_in

ROOT = Path(__file__).resolve().parents[3]
PROMPTS = ROOT / "prompts"
PEOPLE = ("owner", "father")
MOVE_POINTS = 0.05                  # a chance that moves this far (5 points) is a change both people should see
NEWS_DAYS = 14                      # news older than this stays out of a forecast brief
TAG_BATCH = 10                      # same as news_tag.BATCH (a test holds them equal); not imported, the idle path stays small

# ---- GitHub kinds: the workflow file each one starts, and how its payload becomes workflow inputs ---------------------
WORKFLOWS = {
    "load_stock": {"file": "stock-facts.yml", "inputs": {"symbol": "symbol", "exchange": "exchange"}},
    "news_collect": {"file": "news-collect.yml", "inputs": {}},
    "history_backfill": {"file": "history-backfill.yml", "inputs": {"from": "from_year", "to": "to_year"}, "years": ("from", "to")},
    "nightly": {"file": "mechanical-forecast.yml", "inputs": {}},
}


def workflow_inputs(kind: str, payload: dict, job_id: str) -> dict:
    """`gh workflow run -f` inputs for a job. Every mapped workflow declares `job_id` (it names the run, so the check can
    find it again) and the inputs here; GitHub refuses an input a workflow does not declare."""
    spec = WORKFLOWS[kind]
    out = {"job_id": job_id}
    for key, name in spec["inputs"].items():
        value = payload[key]
        out[name] = str(value)[:4] if key in spec.get("years", ()) else str(value)
    return out


# ---- what every kind runs as ----------------------------------------------------------------------------------------
HANDLER_KINDS = ("analyse", "refresh_call", "feedback_read", "news_tag", "news_rank", "weekly_review", "backup", "sync")


def coverage() -> dict[str, str]:
    """kind -> 'handler' or 'workflow' for every kind in the contract; a kind with neither maps to 'none'."""
    out = {}
    for kind in CONTRACT["job_kinds"]:
        out[kind] = "workflow" if kind in WORKFLOWS else "handler" if kind in HANDLER_KINDS else "none"
    return out


# ---- the outside world, replaceable --------------------------------------------------------------------------------
@dataclass
class Deps:
    query: Callable                                   # query(sql, params=()) -> list[dict]
    now: Callable[[], datetime]                       # IST-aware
    state: dict = field(default_factory=dict)         # small facts that must outlive one firing (the Sonnet governor)
    enqueue: Callable | None = None                   # enqueue(kind, payload, asked_by) -> job id
    make_backend: Callable | None = None              # make_backend(name) -> backend with .ask(prompt)
    mechanical: Callable | None = None                # (symbol, exchange) -> {"as_of", "result": {...}} or None
    facts: Callable | None = None                     # (symbol) -> stock facts doc or None
    archive: object | None = None                     # .append(record) and .read() -> list of call dicts
    prices: Callable | None = None                    # (symbols, first_day) -> {symbol: [(date, close)]}
    nifty: Callable | None = None                     # () -> [(date, close)]
    backup: Callable | None = None                    # () -> "Done, ..." words
    hurdle: float = 0.02

    def stamp(self) -> str:
        return self.now().astimezone(IST).replace(microsecond=0).isoformat()


def _prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text()


_json_in = json_in


# ---- analyse and refresh_call ---------------------------------------------------------------------------------------
NO_NUMBERS = ("There are no numbers for this stock yet. The nightly job has not covered it.",
              "এই স্টকের কোনো সংখ্যা এখনও নেই। রাতের কাজ এটি ধরেনি।")
FILING_SOURCES = re.compile(r"\b(nse|bse|filing|exchange)\b", re.I)


def impact_word(n) -> str:
    return "high" if (n or 0) >= 4 else "medium" if (n or 0) == 3 else "low"


def news_for(query, symbol: str, exchange: str, today: date) -> list[dict]:
    since = (datetime.combine(today, datetime.min.time()) - timedelta(days=NEWS_DAYS)).date().isoformat()
    rows = query("select i.id, i.published_at, i.source, i.source_count, i.impact, i.title, i.line_en from news_items i "
                 "join news_tags t on t.item_id = i.id where t.symbol = ? and t.exchange = ? and i.tagged_at is not null "
                 "and substr(i.published_at, 1, 10) >= ? and substr(i.published_at, 1, 10) <= ? "
                 "order by i.published_at desc limit 8", [symbol, exchange, since, today.isoformat()])
    return [{"id": r["id"], "date": r["published_at"][:10], "sources": r["source_count"], "filing": bool(FILING_SOURCES.search(r["source"] or "")),
             "impact": impact_word(r["impact"]), "headline": r["line_en"] or r["title"]} for r in rows]


def build_brief(symbol: str, exchange: str, mech: dict, facts: dict | None, news: list[dict], today: date) -> dict:
    """The model's whole input: the code's start, the facts with ids, the news with ids. Nothing about the owners."""
    r = mech["result"]
    base = {k: r[k] for k in ("chance_3m", "chance_6m", "low_3m", "likely_3m", "high_3m", "low_6m", "likely_6m", "high_6m")}
    f = {}
    if facts:
        td, val, qual = facts.get("today", {}), facts.get("valuation", {}), facts.get("quality", {})
        f["f1"] = {"date": facts.get("as_of"), **{k: v for k, v in {**td, **val, **qual}.items() if v is not None}}
        for i, ev in enumerate(facts.get("events") or [], 2):
            f[f"f{i}"] = {"date": ev["date"], "kind": ev["kind"], "text": ev["text"]}
    price = (facts or {}).get("today", {}).get("last")
    return {"symbol": symbol, "exchange": exchange, "as_of": today.isoformat(), "price": price, "base": base, "facts": f, "news": news,
            "signals": r.get("signals"), "sector": (facts or {}).get("sector")}


def model_seam(model):
    """`analyse(brief, role, errors=None, forecast=None, net=None)` for `forecast_form.forecast_stock`, over a model chain."""
    def analyse(brief, role, errors=None, forecast=None, net=None):
        text = _prompt("forecast_form") + "\n\nRole: " + role + "\n\nBrief:\n" + json.dumps(brief, ensure_ascii=False)
        if errors:
            text += "\n\nYour last form was rejected. Fix these and answer again:\n- " + "\n- ".join(errors)
        if forecast is not None:
            text += "\n\nThe form:\n" + json.dumps(forecast, ensure_ascii=False) + "\nNet move: " + json.dumps(net)
        answer = model.ask(text)
        try:
            data = _json_in(answer)
        except ValueError:
            data = None
        used = getattr(model, "used", None) or getattr(model, "name", None)
        return {"model": used, "net": (data or {}).get("net")} if role == "second_opinion" else {"model": used, "form": data}
    return analyse


def _scale_1m(price: float | None, base: dict) -> dict:
    """The 1-month range when the model gave none (code's own start): the 3-month range scaled, wider with the square root of time."""
    p = price or base["likely_3m"]
    k = 3 ** 0.5
    return {"low_1m": round(p - (p - base["low_3m"]) / k, 2), "likely_1m": round(p + (base["likely_3m"] - p) / 3, 2),
            "high_1m": round(p + (base["high_3m"] - p) / k, 2)}


def calls_row(rec: dict, brief: dict, exchange: str, deps: Deps) -> dict:
    base = brief["base"]
    rng = rec.get("ranges") or {**{k: base[k] for k in base if k.startswith(("low_", "likely_", "high_")) and k.endswith(("3m", "6m"))},
                                **_scale_1m(brief.get("price"), base)}
    ok = rec["status"] == "ok"
    return {"symbol": rec["symbol"], "exchange": exchange, "call": rec["call"], "route": rec["route"],
            "chance_3m": rec["chance_3m"], "chance_6m": rec["chance_6m"], "confidence": rec.get("confidence") or "low", **rng,
            "model": (rec.get("model") or "code") if ok else "code", "form": json.dumps(rec, ensure_ascii=False, default=str),
            "as_of": brief["as_of"], "written_at": deps.stamp(), "out_of_date": 0, "news_buy": int(bool(rec["news_buy"]))}


def archive_record(rec: dict, brief: dict, exchange: str, deps: Deps) -> dict:
    """What `trackrecord` reads later: percents, the start, the 1-month range and the adjustments, one line per call."""
    form = rec.get("raw") or {}
    return {"symbol": rec["symbol"], "exchange": exchange, "made_on": brief["as_of"], "route": rec["route"], "call": rec["call"],
            "chance_3m": round(rec["chance_3m"] * 100), "chance_6m": round(rec["chance_6m"] * 100),
            "base_3m": round(rec["base"]["chance_3m"] * 100), "base_6m": round(rec["base"]["chance_6m"] * 100),
            "price": brief.get("price"), "hurdle": deps.hurdle, "model": rec.get("model") or "code",
            "range_1m": ({"low": rec["ranges"]["low_1m"], "high": rec["ranges"]["high_1m"]} if rec.get("ranges") else None),
            "adjustments": [a for a in form.get("adjustments") or [] if isinstance(a, dict)] if rec["status"] == "ok" else [],
            "news_ids": [n["id"] for n in brief.get("news") or []] if rec["route"] == "news" else []}


def _change(job_id, person, symbol, kind, old, new, reason, reason_bn, at) -> dict:
    return {"id": f"chg_{job_id}_{person}_{kind}", "person": person, "symbol": symbol, "kind": kind, "old_value": old,
            "new_value": new, "reason": reason, "reason_bn": reason_bn, "at": at, "seen_at": None}


def changes_for(job: dict, symbol: str, before: dict | None, rec: dict, at: str) -> list[dict]:
    """The yellow marks of a finished forecast: a changed call or a chance that moved 5 points go to both people; the one
    who asked also gets 'ready'."""
    why = rec.get("summary") or "The model was not available, so this is the code's own start."
    why_bn = rec.get("summary_bn") or "মডেল পাওয়া যায়নি, তাই এটি কোডের নিজের হিসাব।"
    out = []
    if before:
        if before["call"] != rec["call"]:
            out += [_change(job["id"], p, symbol, "call_changed", before["call"], rec["call"], why, why_bn, at) for p in PEOPLE]
        if abs(before["chance_3m"] - rec["chance_3m"]) >= MOVE_POINTS - 1e-9:
            out += [_change(job["id"], p, symbol, "chance_moved", f"{before['chance_3m']:.2f}", f"{rec['chance_3m']:.2f}", why, why_bn, at)
                    for p in PEOPLE]
    if job["asked_by"] in PEOPLE:
        out.append(_change(job["id"], job["asked_by"], symbol, "forecast_ready", None, rec["call"], why, why_bn, at))
    return out


def upsert(query, table: str, row: dict, ignore=False) -> None:
    cols = list(row)
    verb = "insert or ignore" if ignore else "insert or replace"
    query(f"{verb} into {table} ({','.join(cols)}) values ({','.join('?' * len(cols))})", [row[c] for c in cols])


def forecast_handler(deps: Deps):
    """`analyse` and `refresh_call`: brief from the nightly numbers, facts and news; the form; the checks; one `calls` row."""
    def run(ctx):
        from stockpilot import forecast_form
        from stockpilot.calls.decide import Rules
        symbol, exchange = ctx.payload["symbol"], ctx.payload["exchange"]
        ctx.progress("Reading the numbers", "সংখ্যা পড়া হচ্ছে")
        mech = deps.mechanical(symbol, exchange)
        if not mech:
            raise JobFailed(*NO_NUMBERS)
        today = date.fromisoformat(deps.stamp()[:10])
        brief = build_brief(symbol, exchange, mech, deps.facts(symbol) if deps.facts else None, news_for(deps.query, symbol, exchange, today), today)
        ctx.progress(f"Found {len(brief['news'])} news items", f"{len(brief['news'])}টি খবর পাওয়া গেছে")
        ctx.progress("Asking the model", "মডেলকে জিজ্ঞাসা করা হচ্ছে")
        rec = forecast_form.forecast_stock(brief, model_seam(ctx.model), Rules())
        if rec["status"] != "ok":
            ctx.progress("The model's answer failed the checks; using the code's own start", "মডেলের উত্তর যাচাইয়ে টেকেনি; কোডের নিজের হিসাব ব্যবহার হচ্ছে")
        before = (deps.query("select call, chance_3m from calls where symbol = ? and exchange = ?", [symbol, exchange]) or [None])[0]
        upsert(deps.query, "calls", calls_row(rec, brief, exchange, deps))
        if deps.archive is not None:
            deps.archive.append(archive_record(rec, brief, exchange, deps))
        marks = changes_for(ctx.job, symbol, before, rec, deps.stamp())
        for m in marks:
            upsert(deps.query, "changes", m, ignore=True)
        gov = deps.state.get("sonnet")
        if gov and symbol in gov.get("running", []):
            gov["running"].remove(symbol)
        word = "change" if len(marks) == 1 else "changes"
        return f"Done, {len(marks)} {word}"
    return run


# ---- feedback_read --------------------------------------------------------------------------------------------------
READ_FAILED = ("We could not read this message. Please write it again.", "আমরা বার্তাটি পড়তে পারিনি। অনুগ্রহ করে আবার লিখুন।")


def feedback_handler(deps: Deps):
    def run(ctx):
        from stockpilot import feedback_read
        fid = ctx.payload["feedback_id"]
        got = deps.query("select id, person, text from feedback where id = ?", [fid])
        if not got:
            raise JobFailed("That message is not there any more.", "বার্তাটি আর নেই।")
        msg = got[0]
        deps.query("update feedback set status = 'reading' where id = ?", [fid])
        ctx.progress("Reading the message", "বার্তা পড়া হচ্ছে")
        schema = (ROOT / "schemas" / "feedback_read.schema.json").read_text()

        def analyse(brief, role, runners):
            text = (_prompt("feedback_read") + "\n\nAnswer as JSON in this schema:\n" + schema + "\n\nMessage:\n"
                    + json.dumps(brief["message"], ensure_ascii=False))
            return {"decisions": _json_in(ctx.model.ask(text))}
        try:
            asks = feedback_read.read(msg["text"], msg["person"], analyse, [getattr(ctx.model, "used", None) or "model"])
        except feedback_read.ReadError as err:
            if isinstance(err.__cause__, JobFailed):                  # every model was away: not the message's fault, try again later
                deps.query("update feedback set status = 'received' where id = ?", [fid])
                raise err.__cause__ from err
            deps.query("update feedback set status = 'failed' where id = ?", [fid])
            raise JobFailed(READ_FAILED[0], READ_FAILED[1]) from err
        for row in feedback_read.rows(fid, asks, deps.stamp()):
            upsert(deps.query, "asks", {**row, "not_meant": int(row["not_meant"])})
        deps.query("update feedback set status = 'understood' where id = ?", [fid])
        ctx.progress(f"Found {len(asks)} wishes", f"{len(asks)}টি ইচ্ছা পাওয়া গেছে")
        return f"Done, {len(asks)} {'ask' if len(asks) == 1 else 'asks'}"
    return run


# ---- news_tag and news_rank -----------------------------------------------------------------------------------------
def untagged(query, limit=TAG_BATCH) -> list[dict]:
    return query("select id, title, source from news_items where tagged_at is null order by published_at desc limit ?", [limit])


def save_tags(query, tags: list[dict], at: str) -> None:
    for t in tags:
        wide = int(not t["touches"] and not t["sector"])
        query("update news_items set sector = ?, direction = ?, impact = ?, line_en = ?, line_bn = ?, market_wide = ?, tagged_at = ? where id = ?",
              [t["sector"], t["direction"], t["impact"], t["line_en"], t["line_bn"], wide, at, t["id"]])
        for x in t["touches"]:
            upsert(query, "news_tags", {"item_id": t["id"], "symbol": x["symbol"], "exchange": x["exchange"], "relation": x["relation"],
                                         "direction": x["direction"], "size": x["size"], "changes_call": int(x["changes_call"])})


def tag_handler(deps: Deps):
    """Gemini A then B (the chain), and for a batch the first answer got wrong, Haiku."""
    def run(ctx):
        from stockpilot import news_tag
        batch = ctx.payload["batch"]
        ctx.progress(f"Tagging {len(batch)} news items", f"{len(batch)}টি খবরে ট্যাগ বসানো হচ্ছে")
        tags = news_tag.tag_all(batch, ctx.model, deps.make_backend("haiku") if deps.make_backend else None)
        save_tags(deps.query, tags, deps.stamp())
        return f"Done, {len(tags)} tagged"
    return run


def _load_rank(deps: Deps):
    now = deps.now().astimezone(IST)
    since = (now - timedelta(days=3)).isoformat()
    rows = deps.query("select id, published_at, impact, source_count, sector from news_items where tagged_at is not null and published_at >= ?", [since])
    touches: dict[str, list] = {}
    for t in deps.query("select item_id, symbol, exchange from news_tags where item_id in (select id from news_items where tagged_at is not null and published_at >= ?)", [since]):
        touches.setdefault(t["item_id"], []).append({"symbol": t["symbol"], "exchange": t["exchange"]})
    items = [{**r, "touches": touches.get(r["id"], [])} for r in rows]
    lists = deps.query("select list_name, symbol from lists where list_name in ('holdings', 'watchlist')")
    holdings = {r["symbol"] for r in lists if r["list_name"] == "holdings"}
    watch = {r["symbol"] for r in lists if r["list_name"] == "watchlist"}
    sectors = {}
    for sym in holdings | watch | {t["symbol"] for ts in touches.values() for t in ts}:
        facts = deps.facts(sym) if deps.facts else None
        if facts and facts.get("sector"):
            sectors[sym] = facts["sector"]
    return items, holdings, watch, sectors, now


def rank_handler(deps: Deps):
    """Spread, rank, tier, mark, then plan the refreshes: each new high or medium item becomes a `refresh_call` job (Sonnet within
    the caps, else the cheap chain); a low item gets only its newspaper mark."""
    def run(ctx):
        from stockpilot import news_rank
        items, holdings, watch, sectors, now = _load_rank(deps)
        ctx.progress(f"Ranking {len(items)} news items", f"{len(items)}টি খবরের ক্রম ঠিক করা হচ্ছে")
        ranked = news_rank.rank(items, holdings, watch, sectors, now)
        known = {r["item_id"] for r in deps.query("select item_id from news_rank")}
        for r in ranked:
            upsert(deps.query, "news_rank", {k: r[k] for k in ("item_id", "closeness", "score", "tier", "ranked_at")})
        fresh = [r for r in ranked if r["item_id"] not in known]
        started = 0
        if fresh and deps.enqueue:
            st = deps.state.setdefault("sonnet", {"day": now.date().isoformat(), "used": 0, "done": [], "running": []})
            gov = news_rank.SonnetGovernor(date.fromisoformat(st["day"]))
            gov.used_today, gov._done, gov.running = st["used"], set(st["done"]), set(st["running"])
            busy = {(j["payload"]["symbol"]) for j in _open_refreshes(deps.query)}
            for p in news_rank.refresh_plan(fresh, gov, now):
                if p["model"] in (None, "skip") or p["symbol"] in busy:
                    continue
                kind = ("news_high" if p["model"] == "sonnet" else "news_medium")
                exch = next((t["exchange"] for it in items for t in it["touches"] if t["symbol"] == p["symbol"]), "NSE")
                deps.enqueue("refresh_call", {"symbol": p["symbol"], "exchange": exch, "reason": kind}, "system")
                busy.add(p["symbol"])
                started += 1
            st.update(day=gov.day.isoformat(), used=gov.used_today, done=sorted(gov._done), running=sorted(gov.running))
        ctx.progress(f"Planned {started} refreshes", f"{started}টি হালনাগাদের পরিকল্পনা হয়েছে")
        return f"Done, {len(ranked)} ranked"
    return run


def _open_refreshes(query) -> list[dict]:
    rows = query("select payload from jobs where kind = 'refresh_call' and status in ('queued', 'running')")
    return [{"payload": json.loads(r["payload"])} for r in rows]


# ---- weekly_review --------------------------------------------------------------------------------------------------
class JsonlArchive:
    """One line per call, on the VM, kept forever: D1's `calls` holds only the current row per stock."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def append(self, record: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def read(self) -> list[dict]:
        if not self.path.exists():
            return []
        out = []
        for line in self.path.read_text().splitlines():
            if line.strip():
                rec = json.loads(line)
                rec["made_on"] = date.fromisoformat(rec["made_on"])
                out.append(rec)
        return out


def _review_load(deps: Deps):
    def load():
        calls = deps.archive.read() if deps.archive is not None else []
        if not calls:
            return [], {}, [], {}
        first = min(c["made_on"] for c in calls)
        prices = deps.prices(sorted({c["symbol"] for c in calls}), first) if deps.prices else {}
        nifty = deps.nifty() if deps.nifty else []
        ids = {i for c in calls for i in c.get("news_ids") or []}
        news = {}
        for i in sorted(ids):
            got = deps.query("select title, link from news_items where id = ?", [i])
            if got:
                news[i] = got[0]
        return calls, prices, nifty, news
    return load


def _review_save(deps: Deps):
    def save(fb, asks, doc):
        at = deps.stamp()
        if fb:
            upsert(deps.query, "feedback", fb)
        for a in asks:
            upsert(deps.query, "asks", {**a, "not_meant": int(a["not_meant"])})
        old = deps.query("select doc from views where name = 'record'")
        base = json.loads(old[0]["doc"]) if old else {}
        merged = {**base, "track_record": doc}
        upsert(deps.query, "views", {"name": "record", "doc": json.dumps(merged, ensure_ascii=False, default=str),
                                     "as_of": doc["as_of"], "written_at": at})
    return save


def review_handler(deps: Deps):
    def run(ctx):
        from stockpilot import review
        today = lambda: date.fromisoformat(deps.stamp()[:10])
        return review.handler(_review_load(deps), _review_save(deps), today)(ctx)
    return run


# ---- backup ---------------------------------------------------------------------------------------------------------
def backup_handler(deps: Deps):
    def run(ctx):
        ctx.progress("Making the encrypted copy", "এনক্রিপ্ট করা কপি তৈরি হচ্ছে")
        if deps.backup is None:
            raise JobFailed("The backup is not set up on this machine yet.", "এই মেশিনে ব্যাকআপ এখনও সাজানো হয়নি।")
        return deps.backup() or "Done"
    return run


def handlers(deps: Deps) -> dict:
    """Every kind this machine runs itself. (`sync` is added by `minute._handlers` because it needs the Kite worker.)"""
    forecast = forecast_handler(deps)
    return {"analyse": forecast, "refresh_call": forecast, "feedback_read": feedback_handler(deps), "news_tag": tag_handler(deps),
            "news_rank": rank_handler(deps), "weekly_review": review_handler(deps), "backup": backup_handler(deps)}


# ---- what the one-minute check enqueues on its own -----------------------------------------------------------------
def schedule(seen: dict, source, enqueue, now: datetime, ran_tag: bool = False, skip=()) -> list[str]:
    """Jobs nobody presses a button for. Returns the kinds enqueued.
      weekly_review  on Saturdays (IST) from 07:00, once a week;
      news_tag       when untagged news waits and no tag job is open (one batch of 10 a firing; not while its kind is backing off after failures);
      news_rank      after a tag job finished this firing."""
    made = []
    local = now.astimezone(IST)
    last = seen.get("last_weekly")
    if "weekly_review" not in skip and local.weekday() == 5 and local.hour >= 7 and not (last and datetime.fromisoformat(last).astimezone(IST).date() == local.date()):
        enqueue("weekly_review", {}, "system")
        made.append("weekly_review")
    open_kinds = set(seen.get("open_kinds") or ())
    if seen.get("untagged") and "news_tag" not in open_kinds and "news_tag" not in skip:
        batch = source.untagged()
        if batch:
            enqueue("news_tag", {"batch": batch}, "system")
            made.append("news_tag")
    if ran_tag and "news_rank" not in open_kinds:
        enqueue("news_rank", {}, "system")
        made.append("news_rank")
    return made


# ---- production loaders: public files over plain HTTPS, cached on the VM -------------------------------------------------
ENGINE = "gunjannandy/stockpilot-engine"


def fetch_bytes(url: str, timeout=60) -> bytes:
    import urllib.request
    with urllib.request.urlopen(url, timeout=timeout) as resp:  # noqa: S310 - fixed https URLs of the public engine repo
        return resp.read()


def _fresh(path: Path, now: datetime, days: float) -> bool:
    return path.exists() and (now.timestamp() - path.stat().st_mtime) < days * 86400


class PublicFiles:
    """The nightly mechanical results, the weekly stock facts and the price history, from the engine repo's releases."""

    def __init__(self, cache: Path, now: Callable[[], datetime], repo=ENGINE, fetch=fetch_bytes):
        self.cache, self.now, self.repo, self.fetch = Path(cache), now, repo, fetch
        self._mech: tuple[str, dict] | None = None

    def _url(self, tag: str, name: str) -> str:
        return f"https://github.com/{self.repo}/releases/download/{tag}/{name}"

    def _get(self, tag: str, name: str, max_age_days: float) -> Path | None:
        path = self.cache / name
        if not _fresh(path, self.now(), max_age_days):
            try:
                data = self.fetch(self._url(tag, name))
            except Exception:  # noqa: BLE001 - a missing file is "no numbers yet", never a crash
                return path if path.exists() else None
            self.cache.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(path.name + ".part")
            tmp.write_bytes(data)
            tmp.replace(path)
        return path

    def mechanical(self, symbol: str, exchange: str):
        if self._mech is None:
            today = self.now().astimezone(IST).date()
            for back in range(6):
                day = (today - timedelta(days=back)).isoformat()
                path = self._get("mechanical-latest", f"{day}.json", 1)
                if path:
                    doc = json.loads(path.read_text())
                    self._mech = (doc["as_of"], {(r["symbol"], r["exchange"]): r for r in doc["results"]})
                    break
            else:
                self._mech = ("", {})
        as_of, rows = self._mech
        row = rows.get((symbol, exchange))
        return {"as_of": as_of, "result": row} if row else None

    def facts(self, symbol: str):
        import tarfile
        path = self._get("data-latest", "stock-facts.tar.gz", 3)
        if not path:
            return None
        with tarfile.open(path, "r:gz") as tar:
            for member in tar:
                if member.isfile() and member.name.rsplit("/", 1)[-1] == f"{symbol}.json":
                    return json.loads(tar.extractfile(member).read())
        return None

    def prices(self, symbols: list[str], first_day: date) -> dict:
        import duckdb
        files = []
        for year in range(first_day.year, self.now().year + 1):
            path = self._get("history-prices", f"prices-NSE-{year}.parquet", 1 if year == self.now().year else 365)
            if path:
                files.append(str(path))
        if not files or not symbols:
            return {}
        con = duckdb.connect()
        marks = ",".join("?" * len(symbols))
        rows = con.execute(f"select symbol, date, close from read_parquet(?) where exchange = 'NSE' and symbol in ({marks}) and date >= ? "
                           "order by symbol, date", [files, *symbols, first_day]).fetchall()
        out: dict[str, list] = {}
        for sym, day, close in rows:
            out.setdefault(sym, []).append((day, close))
        return out


def nifty_from(store_path: Path):
    """The Nifty 50 closes from the VM's own store (the v1 `index_levels` table); empty when the store is not there."""
    def read():
        import duckdb
        if not Path(store_path).exists():
            return []
        con = duckdb.connect(str(store_path), read_only=True)
        try:
            return con.execute("select date, close from index_levels where name = 'Nifty 50' order by date").fetchall()
        finally:
            con.close()
    return read


def backup_via_sp(root: Path, run=None):
    def go():
        import subprocess
        import sys
        run_ = run or subprocess.run
        done = run_([str(Path(sys.executable).parent / "sp"), "--root", str(root), "backup", "nightly"], capture_output=True, text=True, timeout=900)
        if done.returncode != 0:
            raise JobFailed("The backup did not finish. The owner has been told.", "ব্যাকআপ শেষ হয়নি। মালিককে জানানো হয়েছে।")
        return "Done, backup saved"
    return go


def production_deps(cfg, query, now, state, enqueue, make_backend) -> Deps:
    cache = Path.home() / ".cache" / "stockpilot-minute"
    files = PublicFiles(cache, now, repo=cfg.get("public_data.repo", ENGINE))
    return Deps(query=query, now=now, state=state, enqueue=enqueue, make_backend=make_backend,
                mechanical=files.mechanical, facts=files.facts, archive=JsonlArchive(cfg.root / "data" / "calls-archive.jsonl"),
                prices=files.prices, nifty=nifty_from(cfg.root / cfg.get("store.path", "data/stockpilot.duckdb")),
                backup=backup_via_sp(cfg.root), hurdle=float(cfg.get("forecast.hurdle", 0.02)))
