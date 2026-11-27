import subprocess
import sys

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1] / "runtime"))
from fake_runtime_worker import KEY, FakeRuntimeWorker  # noqa: E402

from stockpilot.io import Door  # noqa: E402
from stockpilot.model import NoModelToken, OverDailyCap, ask, model_for  # noqa: E402
from stockpilot.model.client import claude_command, run_claude  # noqa: E402
from stockpilot.runtime import JobClient  # noqa: E402


def client(w):
    return JobClient(Door("https://x.invalid", KEY, w.transport))


def test_haiku_by_default():
    assert model_for("analyse") == "haiku"


def test_an_ask_runs_the_model_once_and_a_repeat_comes_from_the_cache():
    w = FakeRuntimeWorker(cap=1)
    runs = []

    def runner(brief, model):
        runs.append((brief, model))
        return "Hold."

    first = ask("analyse", "brief one", client=client(w), runner=runner)
    again = ask("analyse", "brief one", client=client(w), runner=runner)
    assert (first.text, first.cached) == ("Hold.", False)
    assert (again.text, again.cached) == ("Hold.", True)
    assert runs == [("brief one", "haiku")]


def test_past_the_daily_cap_the_ask_is_refused_without_running_the_model():
    w = FakeRuntimeWorker(cap=1)
    runs = []
    ask("analyse", "a", client=client(w), runner=lambda b, m: runs.append(b) or "x")
    with pytest.raises(OverDailyCap, match="Next update tomorrow"):
        ask("analyse", "b", client=client(w), runner=lambda b, m: runs.append(b) or "y")
    assert runs == ["a"]


def test_the_cli_runs_with_no_tools_and_the_setup_token():
    cmd = claude_command("haiku")
    assert cmd[:2] == ["claude", "-p"] and cmd[cmd.index("--tools") + 1] == ""
    seen = {}

    def fake_run(args, **kw):
        seen.update(args=args, **kw)
        return subprocess.CompletedProcess(args, 0, stdout=" answer \n", stderr="")

    out = run_claude("the brief", "haiku", run=fake_run, env={"CLAUDE_CODE_OAUTH_TOKEN": "t"})
    assert out == "answer"
    assert seen["input"] == "the brief" and seen["env"]["CLAUDE_CODE_OAUTH_TOKEN"] == "t"


def test_no_token_and_failed_calls_are_plain_errors():
    with pytest.raises(NoModelToken):
        run_claude("b", "haiku", env={})
    bad = lambda args, **kw: subprocess.CompletedProcess(args, 1, stdout="", stderr="rate limited")  # noqa: E731
    with pytest.raises(RuntimeError, match="rate limited"):
        run_claude("b", "haiku", run=bad, env={"CLAUDE_CODE_OAUTH_TOKEN": "t"})
