"""QUEUE (#114): the page's button kinds are D1 jobs. Each kind has a contract entry and a VM handler that does what the
old KV queue's handler did, says it in plain words, and fails in plain words."""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from stockpilot import jobrun, store
from stockpilot.jobs import buttons, minute

ROOT = Path(__file__).resolve().parents[2]
IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 11, 26, 9, 15, tzinfo=IST)
OLD = json.loads((ROOT / "schemas" / "queue-kinds.json").read_text())["kinds"]
MOVED_ELSEWHERE = {"feedback": "feedback_create route", "feedback_decide": "ask_decide route", "ask_analyst": "analyse job"}


def test_every_button_kind_is_a_vm_private_contract_kind_with_the_old_payload_keys():
    kinds = jobrun.CONTRACT["job_kinds"]
    assert set(buttons.BUTTON_KINDS) == set(OLD) - set(MOVED_ELSEWHERE)
    for kind in buttons.BUTTON_KINDS:
        assert kinds[kind]["runs_on"] == "vm_private", kind
        assert kinds[kind]["payload"] == OLD[kind], kind


class Source:
    def __init__(self, rows): self.rows = rows
    def pending(self): return {"queued": self.rows, "last_nightly": "2026-11-26T02:00:00+05:30"}


def job(kind, payload, by="father", i=1):
    return {"id": f"job_{i}", "kind": kind, "payload": payload, "asked_by": by, "status": "queued", "result": None, "error": None,
            "error_bn": None, "created_at": "2026-11-26T09:10:00+05:30", "started_at": None, "finished_at": None}


def fire(db, kind, payload, by="father", **extra):
    sink = jobrun.MemorySink()
    handlers = {k: buttons.handler(k, lambda: db, **extra) for k in buttons.BUTTON_KINDS}
    minute.tick(Source([job(kind, payload, by)]), sink, make_backend=lambda n: None, handlers=handlers,
                start_github=lambda j: None, alarm=lambda t: None, state={}, now=lambda: T0)
    return sink.jobs["job_1"], sink.lines["job_1"]


def test_watchlist_add_then_remove_say_what_happened(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    done, lines = fire(db, "watchlist_add", {"symbol": "SBIN", "exchange": "NSE"})
    assert done["status"] == "done" and done["result"] == "Added SBIN."
    assert db.execute("select added_by from watchlist where symbol = 'SBIN'").fetchone()[0] == "father"      # who pressed it
    assert lines[-1]["state"] == "ok"
    done, _ = fire(db, "watchlist_add", {"symbol": "SBIN", "exchange": "NSE"})
    assert done["result"] == "SBIN was already on the watchlist."
    done, _ = fire(db, "watchlist_remove", {"symbol": "SBIN", "exchange": "NSE"})
    assert done["result"] == "Removed SBIN."


def test_a_bad_request_fails_in_plain_words_in_both_languages(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    failed, lines = fire(db, "watchlist_add", {"symbol": "no way!", "exchange": "NSE"})
    assert failed["status"] == "failed" and failed["error"] == "'no way!' is not a stock symbol."
    assert failed["error_bn"] and lines[-1]["state"] == "fail"


def test_decision_buttons_write_the_store(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    assert fire(db, "budget_set", {"month": "2026-12", "amount": 50000})[0]["result"].startswith("Budget for 2026-12")
    assert fire(db, "long_term_mark", {"symbol": "ITC", "on": True})[0]["result"] == "ITC is marked as held for years."
    assert db.execute("select count(*) from long_term_marks where symbol = 'ITC'").fetchone()[0] == 1
    assert fire(db, "snooze", {"symbol": "TCS", "scope": "any"})[0]["status"] == "done"
    assert fire(db, "allocation_approve", {"target": {"equity": 0.7}})[0]["result"] == "Target allocation approved."
    assert fire(db, "learned_forget", {"pattern": "no-such"})[0]["status"] in ("done", "failed")   # a real handler answered


def test_heavy_buttons_use_what_the_machine_gives_them(tmp_path):
    db = store.open(tmp_path / "sp.duckdb")
    asked = []
    ctx = dict(build_pack=lambda d: "Tax pack for FY 2026-27 is built.", sync_docs=lambda d: "Read 3 documents.",
               rerun=lambda name: asked.append(name))
    assert fire(db, "build_tax_pack", {}, **ctx)[0]["result"] == "Tax pack for FY 2026-27 is built."
    assert fire(db, "refresh_docs", {}, **ctx)[0]["result"] == "Read 3 documents."
    assert fire(db, "rerun", {"job": "daily"}, **ctx)[0]["status"] == "done" and asked == ["daily"]
    assert fire(db, "rerun", {"job": "nope"}, **ctx)[0]["error"] == "'nope' cannot be rerun from here."
    assert "cannot" in fire(db, "build_tax_pack", {})[0]["error"]            # no machine piece, plain words


def test_no_button_handler_can_place_an_order():
    src = (ROOT / "src" / "stockpilot" / "jobs" / "buttons.py").read_text().lower()
    assert "order" not in src.replace("in order", "")


def test_the_one_minute_check_registers_every_button_kind_against_the_real_store(tmp_path):
    from stockpilot import config
    (tmp_path / "data").mkdir()
    cfg = config.load(tmp_path)
    made = minute._button_handlers(cfg, store)
    assert set(made) == set(buttons.BUTTON_KINDS)
    sink = jobrun.MemorySink()
    minute.tick(Source([job("watchlist_add", {"symbol": "SBIN", "exchange": "NSE"})]), sink, make_backend=lambda n: None,
                handlers=made, start_github=lambda j: None, alarm=lambda t: None, state={}, now=lambda: T0)
    assert sink.jobs["job_1"]["result"] == "Added SBIN."
    assert store.open(tmp_path / "data" / "stockpilot.duckdb").execute("select count(*) from watchlist").fetchone()[0] == 1


class StatusWorker:
    def __init__(self, code, body): self.code, self.body = code, body
    def get(self, path):
        assert path == "/api/vm/queue/status"
        return self.code, self.body


def test_the_kv_queue_is_ready_to_retire_only_after_a_quiet_week_with_nothing_waiting():
    from stockpilot import vmqueue
    now = datetime(2026, 12, 10, 9, 0, tzinfo=timezone.utc)
    assert vmqueue.retire_ready(StatusWorker(200, {"last_call_at": None, "pending": 0}), now)[0]
    assert vmqueue.retire_ready(StatusWorker(200, {"last_call_at": "2026-12-01T09:00:00.000Z", "pending": 0}), now)[0]
    assert not vmqueue.retire_ready(StatusWorker(200, {"last_call_at": "2026-12-05T09:00:00.000Z", "pending": 0}), now)[0]
    assert not vmqueue.retire_ready(StatusWorker(200, {"last_call_at": None, "pending": 2}), now)[0]
    assert not vmqueue.retire_ready(StatusWorker(500, {}), now)[0]


def test_every_button_the_page_posts_is_accepted_with_the_payload_the_page_sends(tmp_path):
    """BROWSERFIX: the payloads are copied from web/public/app.js and screens/worth.js. The clock and cross buttons send
    scope "stock" (the page has no buy or sell side), and a funds star sends exchange AMFI."""
    db = store.open(tmp_path / "sp.duckdb")
    page = [("watchlist_add", {"symbol": "SBIN", "exchange": "NSE"}), ("watchlist_add", {"symbol": "INF846K01DP8", "exchange": "AMFI"}),
            ("watchlist_remove", {"symbol": "SBIN", "exchange": "NSE"}), ("snooze", {"symbol": "TCS", "scope": "stock"}),
            ("dismiss", {"symbol": "INFY", "scope": "stock"}), ("long_term_mark", {"symbol": "ITC", "on": True}),
            ("long_term_mark", {"symbol": "ITC", "on": False}), ("budget_set", {"month": "2026-12", "amount": 40000}),
            ("allocation_approve", {"target": {"equity": 0.7}})]
    for kind, payload in page:
        done, _ = fire(db, kind, payload)
        assert done["status"] == "done", (kind, payload, done["error"])
    row = db.execute("select id, scope from not_now where symbol = 'TCS' and undone_at is null").fetchone()
    assert row, "the snooze was not stored"
    done, _ = fire(db, "not_now_undo", {"id": str(row[0])})              # the page sends the id from a data- attribute: a string
    assert done["status"] == "done", done["error"]
