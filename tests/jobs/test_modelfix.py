"""MODELFIX: model jobs run on the VM. Fenced answers parse, one failed backend moves the chain on, the real error reaches
stderr, a failing kind backs off, and the unit fits the box. Every model and process is a fake."""
import json
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from stockpilot import jobrun, news_tag, review
from stockpilot.jobs import minute, wire
from stockpilot.modeljson import json_in

IST = timezone(timedelta(hours=5, minutes=30))
T0 = datetime(2026, 11, 26, 9, 15, tzinfo=IST)
ROOT = Path(__file__).resolve().parents[2]
FENCED = '```json\n[{"id": "n1", "sector": "Banks", "direction": "good", "impact": 3, "line_en": "a", "line_bn": "b", "touches": []}]\n```'


# ---- 3: a fenced or chatty answer parses -------------------------------------------------------------------------------
@pytest.mark.parametrize("text", ['```json\n{"a": 1}\n```', 'Here you go:\n```\n{"a": 1}\n```\nDone.', 'Sure. {"a": 1} Hope that helps.', '{"a": 1}'])
def test_json_in_takes_a_fence_or_surrounding_prose(text):
    assert json_in(text) == {"a": 1}


def test_json_in_refuses_an_answer_with_no_json():
    with pytest.raises(ValueError):
        json_in("I cannot help with that.")


class Fixed:
    name = "haiku"
    def __init__(self, answer): self.answer = answer
    def ask(self, prompt): return self.answer


def test_news_tag_reads_a_fenced_answer():
    tags = news_tag.tag_all([{"id": "n1", "title": "t", "source": "s"}], Fixed(FENCED))
    assert tags[0]["id"] == "n1" and tags[0]["sector"] == "Banks"


def test_weekly_review_reads_an_answer_wrapped_in_prose():
    assert review._parse('Here is my review:\n```json\n{"proposals": []}\n```\nThanks') == []
    assert review._parse('My review. {"proposals": []} End.') == []


def test_the_forecast_and_feedback_seams_still_read_fences():
    assert wire._json_in('```json\n{"net": 1}\n```') == {"net": 1}


# ---- 1, 2: the command each backend runs ----------------------------------------------------------------------------------
class Done:
    def __init__(self, code=0, out="", err=""): self.returncode, self.stdout, self.stderr = code, out, err


def backend(name, results, state=None, now=lambda: T0):
    calls = []

    def run(argv, **kw):
        calls.append((argv, kw))
        got = results.pop(0)
        if isinstance(got, Exception):
            raise got
        return got
    return minute.CliBackend(name, run=run, state=state, now=now), calls


def test_agy_gets_the_prompt_as_the_value_of_p_not_on_stdin():
    b, calls = backend("gemini-a", [Done(out="hi\n")])
    assert b.ask("the prompt") == "hi"
    argv, kw = calls[0]
    assert argv[argv.index("-p") + 1] == "the prompt" and kw.get("input") is None


def test_claude_reads_the_prompt_on_stdin_with_no_tools_no_mcp_and_no_user_settings():
    b, calls = backend("haiku", [Done(out="hi")])
    b.ask("the prompt")
    argv, kw = calls[0]
    assert argv[:4] == ["claude", "-p", "--model", "haiku"] and kw["input"] == "the prompt"
    assert argv[argv.index("--tools") + 1] == "" and "--strict-mcp-config" in argv
    assert argv[argv.index("--setting-sources") + 1] == "project" and "--bare" not in argv


# ---- 2: any failure of one backend moves the chain on -------------------------------------------------------------------
@pytest.mark.parametrize("failure", [Done(2, "", "flag needs an argument: -p"), Done(1, "", "boom"), FileNotFoundError("agy"),
                                       subprocess.TimeoutExpired("agy", 1), Done(1, "Authentication required https://login.example/x?code=abc", "authentication failed or timed out")])
def test_a_failed_backend_hands_the_prompt_to_the_next(failure):
    first, _ = backend("gemini-a", [failure])
    second = type("B", (), {"name": "haiku", "ask": lambda self, p: "ok"})()
    chain = minute.Chain([first, second])
    assert chain.ask("q") == "ok" and chain.used == "haiku"


def test_when_every_backend_fails_for_other_reasons_the_job_says_so_in_plain_words_without_a_url(capsys):
    a, _ = backend("gemini-a", [Done(1, "Authentication required https://login.example/x?code=abc", "")])
    b, _ = backend("haiku", [Done(1, "", "boom")])
    with pytest.raises(jobrun.JobFailed) as err:
        minute.Chain([a, b]).ask("q")
    assert "http" not in err.value.text and err.value.text != minute.QUOTA
    assert "http" not in capsys.readouterr().err


def test_not_logged_in_marks_the_backend_down_for_a_while_so_the_next_firing_does_not_wait_again():
    state = {}
    a, calls = backend("gemini-a", [Done(1, "Authentication required https://x.test/l", "")], state=state)
    with pytest.raises(Exception):
        a.ask("q")
    assert "agy" in state["backend_down"]
    again, calls2 = backend("gemini-b", [], state=state, now=lambda: T0 + timedelta(minutes=5))
    with pytest.raises(minute.Refused):
        again.ask("q")
    assert calls2 == []                                          # agy was not started: gemini-b shares the login
    later, calls3 = backend("gemini-b", [Done(out="ok")], state=state, now=lambda: T0 + timedelta(hours=2))
    assert later.ask("q") == "ok"


# ---- 4: the real error reaches stderr ---------------------------------------------------------------------------------------
class Row(dict): pass


def test_a_failed_job_prints_the_real_exception_scrubbed_to_stderr(capsys):
    sink = jobrun.MemorySink()
    runner = jobrun.JobRunner(sink, clock=lambda: T0)
    runner.register("backup", lambda ctx: (_ for _ in ()).throw(RuntimeError("boom token=abc123 see https://x.test/p?sig=zzz")))
    jid = runner.enqueue("backup", {}, "system")
    runner.run(jid)
    err = capsys.readouterr().err
    assert "RuntimeError" in err and "boom" in err and jid in err
    assert "abc123" not in err and "sig=zzz" not in err
    assert sink.jobs[jid]["error"] == jobrun.GENERIC


# ---- 5: the run fits the box ----------------------------------------------------------------------------------------------
def test_the_batch_is_small_and_the_worst_case_job_fits_inside_the_unit_timeout():
    assert news_tag.BATCH <= 10 and wire.TAG_BATCH == news_tag.BATCH
    unit = (ROOT / "ops/systemd/sp-minute.service").read_text()
    assert "MemoryMax=600M" in unit
    timeout_s = int(next(l for l in unit.splitlines() if l.startswith("TimeoutStartSec=")).split("=")[1].removesuffix("min")) * 60
    worst_job = minute.TIMEOUTS["gemini-a"] + 2 * minute.TIMEOUTS["haiku"]          # agy, haiku, then haiku again for a bad answer
    assert minute.START_BUDGET_S + worst_job < timeout_s


def test_tag_all_does_not_ask_haiku_twice_when_the_chain_already_failed():
    class Dead:
        def ask(self, p): raise jobrun.JobFailed("away")
    class Spy:
        calls = 0
        def ask(self, p): Spy.calls += 1; return "[]"
    with pytest.raises(jobrun.JobFailed):
        news_tag.tag_all([{"id": "n1", "title": "t", "source": "s"}], Dead(), Spy())
    assert Spy.calls == 0


# ---- 6: a kind that keeps failing backs off ----------------------------------------------------------------------------
class Source:
    def __init__(self): self.queued, self.reads = [], 0
    def pending(self): self.reads += 1; return {"queued": list(self.queued), "last_nightly": "2026-11-26T02:00:00+05:30", "untagged": 5, "open_kinds": set()}
    def untagged(self, limit=10): return [{"id": "n1", "title": "t", "source": "s"}]


def fire(source, sink, state, now, ran):
    def handler(ctx):
        ran.append(ctx.job["id"])
        raise RuntimeError("model away")
    made = []
    out = minute.tick(source, sink, make_backend=lambda n: None, handlers={"news_tag": handler}, start_github=lambda j: None,
                      alarm=lambda t: None, state=state, now=lambda: now, enqueue=lambda k, p, by: made.append(k))
    return out, made


def job(i):
    return {"id": f"job_{i}", "kind": "news_tag", "payload": {"batch": []}, "asked_by": "system", "status": "queued", "result": None,
            "error": None, "error_bn": None, "created_at": "2026-11-26T09:00:00+05:30", "started_at": None, "finished_at": None}


def test_a_failed_model_job_backs_the_kind_off_so_it_is_neither_run_nor_enqueued_each_minute():
    src, sink, state, ran = Source(), jobrun.MemorySink(), {}, []
    src.queued = [job(1)]
    out, made = fire(src, sink, state, T0, ran)
    assert out["ran"] == 1 and state["backoff"]["news_tag"]["fails"] == 1
    src.queued = [job(2)]
    out, made = fire(src, sink, state, T0 + timedelta(minutes=1), ran)
    assert out["ran"] == 0 and ran == ["job_1"] and "news_tag" not in made
    out, made = fire(src, sink, state, T0 + timedelta(hours=1), ran)
    assert ran == ["job_1", "job_2"] and state["backoff"]["news_tag"]["fails"] == 2


def test_backoff_grows_and_is_capped_and_a_success_clears_it():
    state = {}
    waits = []
    for _ in range(8):
        minute.note_failure(state, "news_tag", T0)
        waits.append(datetime.fromisoformat(state["backoff"]["news_tag"]["until"]) - T0)
    assert waits == sorted(waits) and waits[-1] == minute.BACKOFF_MAX
    minute.note_success(state, "news_tag")
    assert "news_tag" not in state.get("backoff", {})
