"""R16: a timer unit once failed with 'wrangler: command not found'. Install finds wrangler by absolute path and puts it in the
units; the deploy resolves it the same way and says so plainly when it cannot."""
import subprocess
from pathlib import Path

import pytest

from fakes import make_config
from stockpilot.jobs import ship

ROOT = Path(__file__).parent.parent
INSTALL = ROOT / "ops" / "install.sh"


def _fake_wrangler(tmp_path, where="npm/bin"):
    path = tmp_path / where / "wrangler"
    path.parent.mkdir(parents=True)
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(0o755)
    return path


def _render(tmp_path, *extra, env=None):
    out = tmp_path / "units"
    return out, subprocess.run(["bash", str(INSTALL), "--render", str(out), "--root", str(tmp_path / "proj"), "--user", "nobody", *extra],
                               capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path / "nohome"), **(env or {})})


def test_install_puts_the_absolute_wrangler_path_in_every_unit(tmp_path):
    w = _fake_wrangler(tmp_path)
    out, done = _render(tmp_path, "--wrangler", str(w))
    assert done.returncode == 0, done.stderr
    for name in ("sp-tick.service", "sp-doctor.service", "sp-onfailure.service"):
        text = (out / name).read_text()
        assert f"Environment=WRANGLER={w}" in text, name
        path_line = [ln for ln in text.splitlines() if ln.startswith("Environment=PATH=")][0]
        assert path_line.split("=", 2)[2].startswith(f"{w.parent}:"), path_line
        assert "@" not in text                                    # no placeholder left behind


def test_install_finds_wrangler_on_the_path_when_not_told(tmp_path):
    w = _fake_wrangler(tmp_path)
    out, done = _render(tmp_path, env={"PATH": f"{w.parent}:/usr/bin:/bin"})
    assert done.returncode == 0 and f"Environment=WRANGLER={w}" in (out / "sp-tick.service").read_text()


def test_install_finds_wrangler_in_the_owners_npm_global_folder(tmp_path):
    w = _fake_wrangler(tmp_path, "nohome/.npm-global/bin")
    out, done = _render(tmp_path)
    assert done.returncode == 0 and f"Environment=WRANGLER={w}" in (out / "sp-tick.service").read_text()


def test_a_wrangler_path_that_does_not_run_stops_the_install(tmp_path):
    out, done = _render(tmp_path, "--wrangler", str(tmp_path / "missing" / "wrangler"))
    assert done.returncode != 0 and "wrangler" in done.stderr and not (out / "sp-tick.service").exists()


def test_a_real_install_with_no_wrangler_stops_before_touching_systemd(tmp_path):
    """No --render: it must refuse at the check, before systemctl or /etc, so this is safe to run anywhere."""
    done = subprocess.run(["bash", str(INSTALL), "--root", str(tmp_path / "proj"), "--user", "nobody", "--check-only"],
                          capture_output=True, text=True, env={"PATH": "/usr/bin:/bin", "HOME": str(tmp_path / "nohome")})
    assert done.returncode != 0 and "wrangler was not found" in done.stderr


def test_render_without_wrangler_only_warns(tmp_path):
    out, done = _render(tmp_path)
    assert done.returncode == 0 and "wrangler was not found" in done.stderr
    assert "WRANGLER=\n" not in (out / "sp-tick.service").read_text()      # no empty variable written


# ---- the deploy itself ---------------------------------------------------------------------------------

class Cfg:
    def __init__(self, root, command=None):
        self.root, self._command = root, command

    def get(self, key, default=None):
        return {"deploy.command": self._command, "worker.project": "proj"}.get(key, default)


def _deploy(tmp_path, command=None, monkeypatch=None, env=None, path=None):
    calls = []

    def run(cmd, **kw):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, "", "")
    for k in ("WRANGLER", "PATH"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("PATH", path or "/nowhere")
    for k, v in (env or {}).items():
        monkeypatch.setenv(k, v)
    (tmp_path / "web").mkdir(exist_ok=True)
    return ship.deploy_site(Cfg(tmp_path, command), run=run), calls


def test_deploy_uses_the_wrangler_the_install_recorded(tmp_path, monkeypatch):
    w = _fake_wrangler(tmp_path)
    _, calls = _deploy(tmp_path, monkeypatch=monkeypatch, env={"WRANGLER": str(w)})
    assert calls[0][0] == str(w) and calls[0][1:3] == ["pages", "deploy"]


def test_deploy_resolves_a_bare_name_to_an_absolute_path(tmp_path, monkeypatch):
    w = _fake_wrangler(tmp_path)
    _, calls = _deploy(tmp_path, ["wrangler", "pages", "deploy", "../site"], monkeypatch, path=str(w.parent))
    assert calls[0] == [str(w), "pages", "deploy", "../site"]


def test_an_absolute_command_in_config_is_left_as_it_is(tmp_path, monkeypatch):
    _, calls = _deploy(tmp_path, ["/opt/w/wrangler", "pages", "deploy", "../site"], monkeypatch)
    assert calls[0][0] == "/opt/w/wrangler"


def test_deploy_says_plainly_when_wrangler_is_nowhere(tmp_path, monkeypatch):
    with pytest.raises(RuntimeError, match="wrangler was not found"):
        _deploy(tmp_path, monkeypatch=monkeypatch)
