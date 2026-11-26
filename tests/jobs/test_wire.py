"""WIRE: every job kind in the live contract has a handler or a GitHub workflow, reads and writes D1, falls back down its model
chain, and speaks Bengali where the contract asks. Every model is a fake; the people are "owner" and "father"."""
import json
import re
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
import yaml

from stockpilot import jobrun
from stockpilot.jobs import minute, wire
from stockpilot.jobs.buttons import BUTTON_KINDS
from test_forecast_form import good  # noqa: E402 - tests/ is on the path (pyproject pythonpath)

ROOT = Path(__file__).resolve().parents[2]
IST = timezone(timedelta(hours=5, minutes=30))
NOW = datetime(2026, 11, 25, 9, 15, tzinfo=IST)               # a Wednesday
SATURDAY = datetime(2026, 11, 28, 9, 15, tzinfo=IST)
WORKFLOW_DIR = ROOT / "ops" / "public" / "workflows" if (ROOT / "ops").is_dir() else ROOT / ".github" / "workflows"   # the public code copy lands them in .github
MIGRATIONS = [ROOT / "web" / "migrations" / n for n in ("0001_live_contract.sql", "0002_views.sql")]


def d1():
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    for m in MIGRATIONS:
        db.executescript(m.read_text())

    def query(sql, params=()):
        cur = db.execute(sql, list(params))
        db.commit()
        return [dict(r) for r in cur.fetchall()]
    return db, query


class Scripted:
    """A model that answers by what the prompt asks for. `calls` records the prompts."""

    def __init__(self, name, answers=None, refuse=False):
        self.name, self.answers, self.refuse, self.prompts = name, answers or {}, refuse, []

    def ask(self, prompt):
        self.prompts.append(prompt)
        if self.refuse:
            raise minute.Refused(self.name)
        for marker, answer in self.answers.items():
            if marker in prompt:
                return answer(prompt) if callable(answer) else answer
        raise AssertionError("no scripted answer for: " + prompt[:80])


def tag_answer(prompt):
    ids = re.findall(r"id:(\S+?)\|", prompt)
    return json.dumps([{"id": i, "sector": "Banks", "direction": "good", "impact": 4, "line_en": "Order win.", "line_bn": "অর্ডার জয়।",
                        "touches": [{"symbol": "FIXA", "exchange": "NSE", "relation": "self", "direction": "good", "size": "medium",
                                     "changes_call": True}]} for i in ids])


FEEDBACK_ANSWER = json.dumps({"asks": [{"original": "chart bhalo", "line_en": "Make the chart nicer.", "line_bn": "চার্ট ভালো করুন।",
                                         "tag": "chart", "size": "small", "plan": "Polish the chart."}]})


def forecast_answer(prompt):
    if "Role: second_opinion" in prompt:
        return json.dumps({"net": {"m3": 2, "m6": 3}})
    return json.dumps(good())


MECH = {"symbol": "FIXA", "exchange": "NSE", "chance_3m": 0.50, "chance_6m": 0.52, "low_3m": 90.0, "likely_3m": 104.0, "high_3m": 118.0,
        "low_6m": 85.0, "likely_6m": 108.0, "high_6m": 130.0, "signals": {"momentum": 0.4}}
FACTS = {"symbol": "FIXA", "exchange": "NSE", "name": "Fixa Ltd", "sector": "Banks", "as_of": "2026-11-20", "today": {"last": 100.0},
         "valuation": {"pe": 22}, "quality": {"profit_growth_yoy_pct": 18}, "events": []}


class Rig:
    """A sink and a source on a local D1, handlers with fakes, and a way to fire the one-minute check."""

    def __init__(self, models=None, now=NOW, archive=None):
        self.db, self.query = d1()
        self.sink = jobrun.SqliteSink(minute.D1Db(self.query))
        self.source = minute.D1Source(self.query)
        self.now = now
        self.models = models or {}
        self.github, self.alarms, self.state = [], [], {}
        self.deps = wire.Deps(query=self.query, now=lambda: self.now, state=self.state, make_backend=self.backend,
                              mechanical=lambda s, e: {"as_of": "2026-11-25", "result": MECH} if s == "FIXA" else None,
                              facts=lambda s: FACTS if s == "FIXA" else None, archive=archive, backup=lambda: "Done, backup saved",
                              enqueue=lambda k, p, by: jobrun.JobRunner(self.sink, clock=lambda: self.now).enqueue(k, p, by))
        self.handlers = {**wire.handlers(self.deps), "sync": lambda ctx: "Done, 0 changes", **{k: (lambda ctx: "Done") for k in BUTTON_KINDS}}

    def backend(self, name):
        return self.models.setdefault(name, Scripted(name, {"Tag each news item": tag_answer, "You read one message": FEEDBACK_ANSWER,
                                                              "Forecast form (v2)": forecast_answer, "You are the reviewer": json.dumps({"proposals": []})}))

    def add(self, kind, payload, by="owner"):
        return jobrun.JobRunner(self.sink, clock=lambda: self.now).enqueue(kind, payload, by)

    def fire(self, now=None):
        if now:
            self.now = now
        return minute.tick(self.source, self.sink, make_backend=self.backend, handlers=self.handlers, alarm=self.alarms.append,
                           start_github=lambda j: self.github.append((j["kind"], wire.workflow_inputs(j["kind"], j["payload"], j["id"]))),
                           state=self.state, now=lambda: self.now, enqueue=self.deps.enqueue, check_github=lambda row: self.verdicts.get(row["id"]))

    verdicts: dict = {}

    def job(self, job_id):
        return self.db.execute("select * from jobs where id = ?", [job_id]).fetchone()

    def seed_news(self, item_id="n1", published="2026-11-24T10:00:00+05:30", tagged=True):
        self.db.execute("insert into news_items (id,link,title,source,published_at,group_id,source_count,market_wide,direction,impact,line_en,tagged_at)"
                        " values (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (item_id, "https://x/y", "Fixa wins an order", "Wire", published, item_id, 1, 0, "good", 3, "Order win.",
                         "2026-11-24T11:00:00+05:30" if tagged else None))
        if tagged:
            self.db.execute("insert into news_tags values (?,?,?,?,?,?,?)", (item_id, "FIXA", "NSE", "self", "good", "medium", 0))
        self.db.commit()


# ---- the proof: every contract job kind ----------------------------------------------------------------------------------
SAMPLE = {"sync": {}, "analyse": {"symbol": "FIXA", "exchange": "NSE"},
          "refresh_call": {"symbol": "FIXA", "exchange": "NSE", "reason": "news_high"}, "feedback_read": {"feedback_id": "fb1"},
          "news_tag": {"batch": [{"id": "n9", "title": "Fixa wins an order", "source": "Wire"}]}, "news_rank": {},
          "load_stock": {"symbol": "FIXA", "exchange": "NSE"}, "news_collect": {}, "history_backfill": {"from": "1994-11-03", "to": "2026-11-25"},
          "nightly": {}, "weekly_review": {}, "backup": {},
          "watchlist_add": {"symbol": "FIXA", "exchange": "NSE"}, "watchlist_remove": {"symbol": "FIXA", "exchange": "NSE"},
          "budget_set": {"month": "2026-12", "amount": 1000}, "allocation_approve": {"target": {}}, "refresh_docs": {}, "rerun": {"job": "daily"},
          "build_tax_pack": {}, "not_now": {"symbol": "FIXA", "scope": "any", "for": "week"}, "snooze": {"symbol": "FIXA", "scope": "any"},
          "dismiss": {"symbol": "FIXA", "scope": "any"}, "not_now_undo": {"id": 1}, "learned_forget": {"pattern": "x"},
          "long_term_mark": {"symbol": "FIXA", "on": True}}


def test_every_contract_job_kind_has_a_handler_or_a_workflow():
    kinds = set(jobrun.CONTRACT["job_kinds"])
    assert kinds == set(SAMPLE), "a new job kind needs a sample payload here and a handler or workflow in wire.py"
    assert {k: v for k, v in wire.coverage().items() if v == "none"} == {}, "kinds with neither handler nor workflow"
    rig = Rig()
    for kind, how in wire.coverage().items():
        assert (kind in rig.handlers) if how == "handler" else (kind in wire.WORKFLOWS and kind not in rig.handlers), kind


def test_walk_every_contract_kind_through_the_one_minute_check():
    """Enqueue one job of every kind and fire the check until nothing is left queued: each ends done (VM kinds) or running on
    GitHub with its workflow started (GitHub kinds). Nothing stays queued, nothing fails for want of a handler."""
    rig = Rig()
    rig.seed_news()
    rig.seed_news("n8", tagged=False)
    rig.db.execute("insert into feedback (id,person,text,status,created_at) values ('fb1','father','chart bhalo','received','2026-11-25T08:00:00+05:30')")
    rig.db.commit()
    ids = {kind: rig.add(kind, payload) for kind, payload in SAMPLE.items()}
    for _ in range(3):
        rig.fire()
    for kind, job_id in ids.items():
        row = rig.job(job_id)
        want = "running" if wire.coverage()[kind] == "workflow" else "done"
        assert row["status"] == want, (kind, row["status"], row["error"])
        if row["status"] == "failed":
            assert row["error_bn"], kind
    started = {k for k, _ in rig.github}
    assert started == set(wire.WORKFLOWS)


# ---- GitHub kinds ---------------------------------------------------------------------------------------------------------
def test_each_workflow_exists_declares_the_inputs_it_is_given_and_names_its_run_after_the_job():
    for kind, spec in wire.WORKFLOWS.items():
        doc = yaml.safe_load((WORKFLOW_DIR / spec["file"]).read_text())
        on = doc.get(True) or doc.get("on")                                    # YAML reads a bare `on` as True
        declared = set(on["workflow_dispatch"]["inputs"])
        given = set(wire.workflow_inputs(kind, SAMPLE[kind], "job_1"))
        assert given <= declared, (kind, given - declared)
        assert "inputs.job_id" in doc["run-name"], kind


def test_history_backfill_passes_years_not_dates():
    got = wire.workflow_inputs("history_backfill", {"from": "1994-11-03", "to": 2026}, "job_1")
    assert got == {"job_id": "job_1", "from_year": "1994", "to_year": "2026"}


def test_a_started_github_job_is_closed_when_its_run_finishes():
    rig = Rig()
    job_id = rig.add("news_collect", {})
    rig.fire()
    assert rig.job(job_id)["status"] == "running"
    rig.verdicts = {job_id: None}
    assert rig.fire().get("finished") is None and rig.job(job_id)["status"] == "running"
    rig.verdicts = {job_id: "success"}
    assert rig.fire()["finished"] == 1
    row = rig.job(job_id)
    assert row["status"] == "done" and row["result"] == "Done"
    seqs = [r["seq"] for r in rig.query("select seq from job_lines where job_id = ? order by seq", [job_id])]
    assert seqs == [1, 2]
    rig.verdicts = {}


def test_a_failed_github_run_fails_the_job_in_both_languages():
    rig = Rig()
    job_id = rig.add("nightly", {})
    rig.fire()
    rig.verdicts = {job_id: "failure"}
    rig.fire()
    row = rig.job(job_id)
    assert row["status"] == "failed" and row["error"] and row["error_bn"]
    rig.verdicts = {}


def test_gh_checker_finds_the_run_by_its_title():
    runs = [{"displayTitle": "job_9", "status": "completed", "conclusion": "success"}, {"displayTitle": "job_8", "status": "in_progress", "conclusion": ""}]

    class Done: returncode, stdout = 0, json.dumps(runs)
    check = minute.gh_checker(wire.WORKFLOWS, run=lambda *a, **k: Done())
    assert check({"id": "job_9", "kind": "news_collect"}) == "success"
    assert check({"id": "job_8", "kind": "news_collect"}) is None


def test_gh_starter_sends_the_engine_repo_and_renamed_inputs():
    seen = []

    class Done: returncode, stderr = 0, ""
    minute.gh_starter(wire.WORKFLOWS, run=lambda a, **k: seen.append(a) or Done())(
        {"id": "job_1", "kind": "history_backfill", "payload": {"from": "1994-11-03", "to": "2026-11-25"}})
    args = seen[0]
    assert args[:4] == ["gh", "workflow", "run", "history-backfill.yml"] and "gunjannandy/stockpilot-engine" in args
    assert "from_year=1994" in args and "job_id=job_1" in args and not any(a.startswith("from=") for a in args)


# ---- analyse and refresh_call ---------------------------------------------------------------------------------------------
def test_analyse_writes_the_calls_row_the_archive_and_the_asker_mark(tmp_path):
    archive = wire.JsonlArchive(tmp_path / "calls.jsonl")
    rig = Rig(archive=archive)
    rig.seed_news()
    job_id = rig.add("analyse", {"symbol": "FIXA", "exchange": "NSE"}, by="father")
    rig.fire()
    job = rig.job(job_id)
    assert job["status"] == "done" and job["result"] == "Done, 1 change"
    call = rig.db.execute("select * from calls where symbol = 'FIXA'").fetchone()
    assert call["model"] == "sonnet" and call["call"] == "wait" and call["as_of"] == "2026-11-25" and call["out_of_date"] == 0
    assert call["low_1m"] < call["likely_1m"] < call["high_1m"] and json.loads(call["form"])["status"] == "ok"
    marks = rig.db.execute("select person, kind, reason_bn from changes").fetchall()
    assert [(m["person"], m["kind"]) for m in marks] == [("father", "forecast_ready")] and marks[0]["reason_bn"]
    kept = archive.read()
    assert len(kept) == 1 and kept[0]["made_on"] == date(2026, 11, 25) and kept[0]["chance_3m"] == 52 and kept[0]["base_3m"] == 50
    assert kept[0]["adjustments"] and kept[0]["range_1m"]["low"] == 96


def test_forecast_prompt_holds_no_owner_data_and_no_scores():
    rig = Rig()
    rig.seed_news()
    rig.db.execute("insert into lists values ('holdings','FIXA','NSE',1,'held','','2026-11-01T00:00:00+05:30')")
    rig.add("analyse", {"symbol": "FIXA", "exchange": "NSE"})
    rig.fire()
    text = rig.models["sonnet"].prompts[0].lower()
    assert "holding" not in text.replace("holdings only", "") or "broken_reason" in text      # the form's own key, not a list
    assert "brier" not in text and "track_record" not in text


def test_analyse_falls_to_gemini_when_sonnet_refuses_and_records_that_model():
    rig = Rig({"sonnet": Scripted("sonnet", refuse=True)})
    rig.seed_news()
    rig.models["gemini-a"] = Scripted("gemini-a", {"Forecast form (v2)": forecast_answer})
    job_id = rig.add("analyse", {"symbol": "FIXA", "exchange": "NSE"})
    rig.fire()
    assert rig.job(job_id)["status"] == "done"
    assert rig.db.execute("select model from calls").fetchone()["model"] == "gemini-a"


def test_a_form_that_fails_the_checks_still_gives_the_code_own_start_and_says_so():
    rig = Rig({"sonnet": Scripted("sonnet", {"Forecast form (v2)": "not json at all"})})
    job_id = rig.add("analyse", {"symbol": "FIXA", "exchange": "NSE"})
    rig.fire()
    assert rig.job(job_id)["status"] == "done"
    call = rig.db.execute("select * from calls").fetchone()
    assert call["model"] == "code" and call["call"] == "wait" and call["chance_3m"] == 0.50
    assert call["low_1m"] < call["likely_1m"] < call["high_1m"]
    lines = [r["text"] for r in rig.query("select text from job_lines where job_id = ? order by seq", [job_id])]
    assert any("code's own start" in t for t in lines)


def test_analyse_of_a_stock_with_no_numbers_fails_in_both_languages():
    rig = Rig()
    job_id = rig.add("analyse", {"symbol": "ZZZ", "exchange": "NSE"})
    rig.fire()
    row = rig.job(job_id)
    assert row["status"] == "failed" and row["error"] == wire.NO_NUMBERS[0] and row["error_bn"] == wire.NO_NUMBERS[1]


def test_a_call_that_changes_marks_both_people():
    rig = Rig()
    rig.db.execute("insert into calls values ('FIXA','NSE','buy','code',0.60,0.60,'low',1,2,3,1,2,3,1,2,3,'code','{}','2026-11-24','2026-11-24T20:00:00+05:30',0,0)")
    rig.db.commit()
    rig.add("refresh_call", {"symbol": "FIXA", "exchange": "NSE", "reason": "news_high"}, by="system")
    rig.fire()
    kinds = sorted((m["person"], m["kind"]) for m in rig.db.execute("select person, kind from changes"))
    assert kinds == [("father", "call_changed"), ("father", "chance_moved"), ("owner", "call_changed"), ("owner", "chance_moved")]


def test_medium_news_refresh_takes_the_cheap_chain_and_other_refreshes_the_forecast_chain():
    names = lambda payload: [b.name for b in minute.chain_for("refresh_call", lambda n: Scripted(n), payload).backends]  # noqa: E731
    assert names({"reason": "news_medium"}) == ["gemini-a", "gemini-b", "haiku"]
    assert names({"reason": "news_high"}) == ["sonnet", "gemini-a"] and names({"reason": "hand"}) == ["sonnet", "gemini-a"]


# ---- feedback_read --------------------------------------------------------------------------------------------------------
def test_feedback_read_writes_asks_with_bengali_and_marks_the_message():
    rig = Rig()
    rig.db.execute("insert into feedback (id,person,text,status,created_at) values ('fb1','father','chart bhalo','received','2026-11-25T08:00:00+05:30')")
    rig.db.commit()
    job_id = rig.add("feedback_read", {"feedback_id": "fb1"}, by="father")
    rig.fire()
    assert rig.job(job_id)["status"] == "done"
    ask = rig.db.execute("select * from asks").fetchone()
    assert ask["id"] == "fb1_a1" and ask["line_bn"] and ask["route"] == "auto" and ask["tag"] == "chart"
    assert rig.db.execute("select status from feedback").fetchone()[0] == "understood"
    assert rig.models["gemini-a"].prompts and "chart bhalo" in rig.models["gemini-a"].prompts[0]


def test_feedback_that_cannot_be_read_fails_visibly_and_stays_unread():
    rig = Rig({"gemini-a": Scripted("gemini-a", {"You read one message": json.dumps({"asks": []})})})
    rig.db.execute("insert into feedback (id,person,text,status,created_at) values ('fb1','owner','hmm','received','2026-11-25T08:00:00+05:30')")
    rig.db.commit()
    job_id = rig.add("feedback_read", {"feedback_id": "fb1"})
    rig.fire()
    row = rig.job(job_id)
    assert row["status"] == "failed" and row["error_bn"] and rig.db.execute("select status from feedback").fetchone()[0] == "failed"


def test_feedback_waits_for_a_later_try_when_every_model_is_away():
    rig = Rig({n: Scripted(n, refuse=True) for n in ("gemini-a", "gemini-b", "haiku")})
    rig.db.execute("insert into feedback (id,person,text,status,created_at) values ('fb1','owner','hmm','received','2026-11-25T08:00:00+05:30')")
    rig.db.commit()
    job_id = rig.add("feedback_read", {"feedback_id": "fb1"})
    rig.fire()
    assert rig.job(job_id)["error"] == minute.QUOTA and rig.db.execute("select status from feedback").fetchone()[0] == "received"


# ---- news_tag and news_rank -----------------------------------------------------------------------------------------------
def test_news_tag_saves_tags_and_the_next_firing_ranks_them():
    rig = Rig()
    rig.seed_news("n8", published="2026-11-25T08:00:00+05:30", tagged=False)
    rig.db.execute("insert into lists values ('holdings','FIXA','NSE',1,'held','','2026-11-01T00:00:00+05:30')")
    rig.db.commit()
    first = rig.fire()
    assert first["enqueued"] == ["news_tag"]                              # untagged news waiting, nobody asked
    second = rig.fire()                                                   # the tag job runs; news_rank is enqueued after it
    assert second["ran"] == 1 and second["enqueued"] == ["news_rank"]
    item = rig.db.execute("select * from news_items where id = 'n8'").fetchone()
    assert item["tagged_at"] and item["line_bn"] and item["impact"] == 4
    assert rig.db.execute("select symbol, relation from news_tags").fetchone()["symbol"] == "FIXA"
    rig.fire()
    rank = rig.db.execute("select * from news_rank").fetchone()
    assert rank["item_id"] == "n8" and rank["tier"] == "high" and rank["closeness"] == "holding"


def test_news_tag_uses_haiku_for_a_batch_the_first_answer_got_wrong():
    rig = Rig({"gemini-a": Scripted("gemini-a", {"Tag each news item": "[]"})})
    rig.seed_news("n8", tagged=False)
    job_id = rig.add("news_tag", {"batch": [{"id": "n8", "title": "t", "source": "s"}]}, by="system")
    rig.fire()
    assert rig.job(job_id)["status"] == "done" and rig.models["haiku"].prompts


def test_no_more_than_one_tag_job_is_open_and_an_idle_firing_is_one_read():
    rig = Rig()
    rig.seed_news("n8", tagged=False)
    rig.handlers.pop("news_tag")                                          # leave it queued
    assert rig.fire()["enqueued"] == ["news_tag"]
    assert "enqueued" not in rig.fire()
    idle = Rig()
    reads = []
    idle.source.query = lambda sql, params=(): reads.append(sql) or idle.query(sql, params)
    out = idle.fire()
    assert len(reads) == 1 and out == {"ran": 0, "started": 0, "alarm": False}


def test_high_news_on_a_holding_plans_a_sonnet_refresh_capped_at_the_governor():
    rig = Rig()
    rig.db.execute("insert into lists values ('holdings','FIXA','NSE',1,'held','','2026-11-01T00:00:00+05:30')")
    for i in range(8):
        rig.db.execute("insert into lists values ('holdings',?,'NSE',?,'held','','2026-11-01T00:00:00+05:30')", (f"S{i}", i + 2))
    rig.db.commit()
    for i, sym in enumerate(["FIXA"] + [f"S{i}" for i in range(8)]):
        rig.db.execute("insert into news_items (id,link,title,source,published_at,group_id,source_count,market_wide,direction,impact,tagged_at)"
                       " values (?,?,?,?,?,?,?,?,?,?,?)", (f"x{i}", "l", "t", "s", "2026-11-25T08:00:00+05:30", f"x{i}", 2, 0, "good", 5, "2026-11-25T08:30:00+05:30"))
        rig.db.execute("insert into news_tags values (?,?,?,?,?,?,?)", (f"x{i}", sym, "NSE", "self", "good", "large", 1))
    rig.db.commit()
    rig.add("news_rank", {}, by="system")
    rig.fire()
    reasons = [json.loads(r["payload"])["reason"] for r in rig.db.execute("select payload from jobs where kind = 'refresh_call'")]
    assert reasons.count("news_high") == 2 and reasons.count("news_medium") == 7     # 2 at once; the rest take the cheap route
    assert rig.state["sonnet"]["used"] == 2
    again = rig.db.execute("select count(*) from jobs where kind = 'refresh_call'").fetchone()[0]
    rig.add("news_rank", {}, by="system")
    rig.fire()
    assert rig.db.execute("select count(*) from jobs where kind = 'refresh_call'").fetchone()[0] == again   # already ranked: no repeat


# ---- weekly_review --------------------------------------------------------------------------------------------------------
def test_saturday_enqueues_one_weekly_review_and_other_days_none():
    rig = Rig(now=NOW)
    assert "enqueued" not in rig.fire()
    out = rig.fire(SATURDAY)
    assert out["enqueued"] == ["weekly_review"]
    assert "enqueued" not in rig.fire(SATURDAY + timedelta(hours=3))              # the review ran; not again the same day
    assert rig.db.execute("select count(*) from jobs where kind = 'weekly_review'").fetchone()[0] == 1
    assert rig.job(rig.db.execute("select id from jobs where kind = 'weekly_review'").fetchone()[0])["status"] == "done"


def test_weekly_review_scores_the_archive_and_writes_the_record_view_and_asks(tmp_path):
    archive = wire.JsonlArchive(tmp_path / "calls.jsonl")
    start = date(2026, 1, 5)
    for i in range(3):
        archive.append({"symbol": "FIXA", "exchange": "NSE", "made_on": (start + timedelta(days=i)).isoformat(), "route": "code", "call": "buy",
                        "chance_3m": 70, "chance_6m": 65, "base_3m": 60, "base_6m": 60, "price": 100.0, "hurdle": 0.02, "model": "sonnet",
                        "range_1m": {"low": 95.0, "high": 112.0}, "adjustments": [{"area": "news", "from_evidence": "n1", "points": 3, "horizon": "m3"}],
                        "news_ids": []})
    rig = Rig(archive=archive)
    series = lambda a, b: [(start + timedelta(d), a + (b - a) * d / 400) for d in range(401)]  # noqa: E731
    rig.deps.prices = lambda symbols, first: {"FIXA": series(100, 140)}
    rig.deps.nifty = lambda: series(1000, 1040)
    rig.db.execute("insert into views values ('record', ?, '2026-11-01', '2026-11-01T00:00:00+05:30')", (json.dumps({"headline": "Kept"}),))
    rig.db.commit()
    rig.models["sonnet"] = Scripted("sonnet", {"You are the reviewer": json.dumps({"proposals": []})})
    job_id = rig.add("weekly_review", {}, by="system")
    rig.fire()
    assert rig.job(job_id)["status"] == "done", rig.job(job_id)["error"]
    doc = json.loads(rig.db.execute("select doc from views where name = 'record'").fetchone()[0])
    assert doc["headline"] == "Kept" and doc["track_record"]["track_record"]["code"]["3m"]["n"] == 3       # merged, nothing lost
    assert rig.db.execute("select as_of from views where name = 'record'").fetchone()[0] == "2026-11-25"


# ---- backup, sync, idle cost ----------------------------------------------------------------------------------------------
def test_backup_job_runs_the_backup_and_fails_in_words_when_it_is_not_set_up():
    rig = Rig()
    ok = rig.add("backup", {}, by="system")
    rig.fire()
    assert rig.job(ok)["status"] == "done" and rig.job(ok)["result"] == "Done, backup saved"
    rig.deps.backup = None
    bad = rig.add("backup", {}, by="system")
    rig.fire()
    assert rig.job(bad)["status"] == "failed" and rig.job(bad)["error_bn"]


def test_sync_is_registered_when_the_vm_key_and_worker_url_are_set(tmp_path):
    from stockpilot import config
    (tmp_path / "config").mkdir()
    (tmp_path / "config" / "stockpilot.yaml").write_text("worker:\n  url: https://example.test\n")
    (tmp_path / ".env").write_text("SP_VM_KEY=k\n")
    rig = Rig()
    assert "sync" in minute._handlers(config.load(tmp_path), rig.deps)
    (tmp_path / ".env").write_text("")
    assert "sync" not in minute._handlers(config.load(tmp_path), rig.deps)


def test_importing_the_idle_path_does_not_load_the_heavy_modules():
    import subprocess
    import sys
    code = ("import sys\nfrom stockpilot.jobs import minute, wire\n"
            "heavy = [m for m in ('duckdb', 'pandas', 'numpy', 'stockpilot.forecast_form', 'stockpilot.review', 'stockpilot.news_rank', "
            "'stockpilot.feedback_read', 'stockpilot.news_tag', 'stockpilot.store') if m in sys.modules]\nprint(heavy)")
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                          env={"PATH": "/usr/bin:/bin", "PYTHONPATH": ":".join(sys.path)})
    assert done.stdout.strip() == "[]", done.stdout + done.stderr


def test_public_loaders_cache_and_read_one_stock(tmp_path):
    import io
    import tarfile
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        blob = json.dumps(FACTS).encode()
        info = tarfile.TarInfo("./stock/FIXA.json")
        info.size = len(blob)
        tar.addfile(info, io.BytesIO(blob))
    mech = json.dumps({"as_of": "2026-11-25", "results": [MECH]}).encode()
    asked = []

    def fetch(url):
        asked.append(url)
        if url.endswith("2026-11-25.json"):
            return mech
        if url.endswith("stock-facts.tar.gz"):
            return buf.getvalue()
        raise OSError("404")
    files = wire.PublicFiles(tmp_path, lambda: NOW, fetch=fetch)
    assert files.mechanical("FIXA", "NSE")["result"]["chance_3m"] == 0.50 and files.mechanical("NOPE", "NSE") is None
    assert files.facts("FIXA")["sector"] == "Banks" and files.facts("NOPE") is None
    assert files.facts("FIXA") and sum(u.endswith("stock-facts.tar.gz") for u in asked) == 1      # cached on the VM
    assert all("gunjannandy/stockpilot-engine" in u for u in asked)
