"""T1: the code copy to the public engine repo. Planted strings must block it."""
import subprocess

import pytest

from stockpilot import publish


# Planted strings are built at run time so this file itself passes the scan.
PLANTED_PAN = "QWERT" + "9876Z"
PLANTED_EMAIL = "someone" + "@example.org"
PLANTED_ACCOUNT = "bank acc" + "ount 1234" + "56789012"


def make_tree(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


CLEAN = {
    "src/stockpilot/a.py": "x = 1\n",
    "tests/test_a.py": "def test_a():\n    assert True\n",
    "web/package.json": "{}\n",
    "pyproject.toml": "[project]\nname='x'\n",
}


def test_copies_only_allow_listed_paths(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    make_tree(src, {**CLEAN, "docs/notes.md": "private notes", "private/h.csv": "a", "config/vault.pub": "k", ".env": "S=1"})
    copied = publish.export(src, dest, deny_terms=[])
    assert sorted(copied) == ["pyproject.toml", "src/stockpilot/a.py", "tests/test_a.py", "web/package.json"]
    assert not (dest / "docs").exists() and not (dest / ".env").exists() and not (dest / "private").exists()


def test_planted_pan_blocks_the_copy(tmp_path):
    src, dest = tmp_path / "src", tmp_path / "dest"
    make_tree(src, {**CLEAN, "src/stockpilot/b.py": f"pan = '{PLANTED_PAN}'\n"})
    with pytest.raises(publish.Blocked) as err:
        publish.export(src, dest, deny_terms=[])
    assert [(f.path, f.rule) for f in err.value.findings] == [("src/stockpilot/b.py", "pan")]
    assert not dest.exists()


def test_planted_email_and_account_number_block(tmp_path):
    src = tmp_path / "src"
    make_tree(src, {**CLEAN, "tests/c.py": f"mail = '{PLANTED_EMAIL}'\n{PLANTED_ACCOUNT}\n"})
    rules = {f.rule for f in publish.scan(src, deny_terms=[])}
    assert rules == {"email", "account-number"}


def test_noreply_and_placeholder_emails_are_fine(tmp_path):
    src = tmp_path / "src"
    make_tree(src, {**CLEAN, "tests/c.py": "a = 'noreply@anthropic.com'\nb = 'user@example.com'\n"})
    assert publish.scan(src, deny_terms=[]) == []


def test_deny_terms_match_case_insensitively_and_findings_never_echo_them(tmp_path):
    src = tmp_path / "src"
    make_tree(src, {**CLEAN, "src/stockpilot/d.py": "# for Zorblax Quux\n"})
    found = publish.scan(src, deny_terms=["zorblax quux"])
    assert [(f.path, f.line, f.rule) for f in found] == [("src/stockpilot/d.py", 2 - 1, "deny-term")]
    assert "zorblax" not in repr(found).lower()


def test_private_paths_inside_allowed_folders_block(tmp_path):
    src = tmp_path / "src"
    make_tree(src, {**CLEAN, "tests/private/holdings.csv": "a\n", "web/.env": "K=1\n", "src/stockpilot/vault.age": "x"})
    rules = {(f.path, f.rule) for f in publish.scan(src, deny_terms=[])}
    assert rules == {("tests/private/holdings.csv", "private-path"), ("web/.env", "private-path"), ("src/stockpilot/vault.age", "private-path")}


def test_placeholders_and_unlabelled_numbers_pass(tmp_path):
    src = tmp_path / "src"
    make_tree(src, {**CLEAN, "tests/p.py": "pan = 'AAAAA0000A'\nother = 'ABCDE1234F'\nts = 1700000000000\nmail = 'a@zerodha.net'\n"})
    assert publish.scan(src, deny_terms=[]) == []


def test_code_may_name_private_folders(tmp_path):
    src = tmp_path / "src"
    make_tree(src, {**CLEAN, "src/stockpilot/e.py": "open('data/archive/calls.db')  # reads .env\n"})
    assert publish.scan(src, deny_terms=[]) == []


def test_deny_terms_load_from_file_ignoring_comments(tmp_path):
    f = tmp_path / "deny.txt"
    f.write_text("# names\nAlpha Beta\n\n  gamma \n")
    assert publish.load_deny_terms(f) == ["Alpha Beta", "gamma"]
    assert publish.load_deny_terms(tmp_path / "missing.txt") is None


def test_publish_without_deny_file_refuses(tmp_path):
    src = tmp_path / "src"
    make_tree(src, CLEAN)
    with pytest.raises(publish.Blocked, match="deny list"):
        publish.run(src, remote=str(tmp_path / "r.git"), deny_file=tmp_path / "none.txt", workdir=tmp_path / "w")


def git(*a, cwd):
    return subprocess.run(["git", *a], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def test_publish_starts_fresh_history_then_adds_snapshots(tmp_path):
    src, remote = tmp_path / "src", tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    make_tree(src, CLEAN)
    deny = tmp_path / "deny.txt"
    deny.write_text("# none\n")
    publish.run(src, remote=str(remote), deny_file=deny, workdir=tmp_path / "w1", message="code copy")
    make_tree(src, {"src/stockpilot/a.py": "x = 2\n"})
    publish.run(src, remote=str(remote), deny_file=deny, workdir=tmp_path / "w2", message="code copy")
    log = git("log", "--format=%an|%ae|%s", cwd=remote).splitlines()
    assert log == ["stockpilot-publisher|noreply@users.noreply.github.com|code copy"] * 2
    assert git("show", "main:src/stockpilot/a.py", cwd=remote) == "x = 2"


def test_blocked_publish_pushes_nothing(tmp_path):
    src, remote = tmp_path / "src", tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    make_tree(src, {**CLEAN, "src/stockpilot/b.py": f"pan = '{PLANTED_PAN}'\n"})
    deny = tmp_path / "deny.txt"
    deny.write_text("x-never-present\n")
    with pytest.raises(publish.Blocked):
        publish.run(src, remote=str(remote), deny_file=deny, workdir=tmp_path / "w")
    assert subprocess.run(["git", "rev-parse", "main"], cwd=remote, capture_output=True).returncode != 0


# --- the public repo's workflows -------------------------------------------------

import re
from pathlib import Path

WORKFLOWS = sorted((Path(__file__).parent.parent / publish.PUBLIC_WORKFLOWS).glob("*.yml"))


def test_public_workflows_exist():
    assert {w.name for w in WORKFLOWS} == {"ci.yml", "keep-alive.yml"}


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda w: w.name)
def test_every_action_is_pinned_by_sha(wf):
    uses = re.findall(r"^\s*-?\s*uses:\s*(\S+)", wf.read_text(), re.M)
    assert uses or wf.name == "keep-alive.yml"
    for u in uses:
        assert re.fullmatch(r"[\w.-]+/[\w.-]+@[0-9a-f]{40}", u), u


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda w: w.name)
def test_permissions_are_declared_and_minimal(wf):
    text = wf.read_text()
    top = text.split("\njobs:")[0]
    assert re.search(r"^permissions:", top, re.M), "top-level permissions missing"
    assert "write-all" not in text and "contents: write" not in text


@pytest.mark.parametrize("wf", WORKFLOWS, ids=lambda w: w.name)
def test_public_repo_holds_no_cloudflare_token_and_does_not_deploy(wf):
    text = wf.read_text().lower()
    for word in ("cloudflare", "wrangler", "secrets.", "pages deploy", "pull_request_target"):
        assert word not in text, word


def test_keep_alive_is_scheduled():
    text = (Path(__file__).parent.parent / publish.PUBLIC_WORKFLOWS / "keep-alive.yml").read_text()
    assert "schedule:" in text and "cron:" in text and "actions: write" in text


def test_cli_publish_reports_findings_without_echoing_them(tmp_path, capsys, monkeypatch):
    from stockpilot import cli
    src = tmp_path / "src"
    make_tree(src, {**CLEAN, "src/stockpilot/b.py": f"pan = '{PLANTED_PAN}'\n"})
    (tmp_path / "deny.txt").write_text("# none\n")
    make_tree(src, {"config/stockpilot.yaml": "runner: claude\n"})
    code = cli.main(["--root", str(src), "publish", "--remote", str(tmp_path / "r.git"), "--deny-file", str(tmp_path / "deny.txt")])
    out = capsys.readouterr()
    assert code == 1
    assert "src/stockpilot/b.py:1 pan" in out.err and PLANTED_PAN not in out.err + out.out


def test_publish_from_a_ref_ignores_the_working_tree(tmp_path):
    repo, remote = tmp_path / "repo", tmp_path / "remote.git"
    subprocess.run(["git", "init", "--bare", "-b", "main", str(remote)], check=True, capture_output=True)
    make_tree(repo, CLEAN)
    git("init", "-b", "main", cwd=repo)
    git("add", "-A", cwd=repo)
    git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-m", "c", cwd=repo)
    make_tree(repo, {"src/stockpilot/a.py": f"pan = '{PLANTED_PAN}'\n"})  # uncommitted, must not leave
    (repo / "data").mkdir()
    (repo / "data" / "publish-deny.txt").write_text("# none\n")
    publish.run(repo, remote=str(remote), ref="main", workdir=tmp_path / "w")
    assert git("show", "main:src/stockpilot/a.py", cwd=remote) == "x = 1"
