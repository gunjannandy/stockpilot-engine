"""Playwright pass over the built dashboard (desktop and phone), with a mock API. Needs node and playwright;
the brief says run it only while the VM has 300 MB free, so it skips itself below that."""
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _free_mb():
    for line in open("/proc/meminfo"):
        if line.startswith("MemAvailable"):
            return int(line.split()[1]) // 1024
    return 0


def _has_playwright():
    return shutil.which("node") and subprocess.run(
        ["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _has_playwright(), reason="node playwright not installed")
@pytest.mark.skipif(_free_mb() < 300, reason="needs 300 MB free")
def test_every_tab_renders_and_every_button_posts_the_right_request(tmp_path):
    subprocess.run([sys.executable, str(ROOT / "tests" / "build_site_v10.py"), str(tmp_path / "site")],
                   check=True, cwd=ROOT / "tests", capture_output=True)
    shots = Path(os.environ.get("SP_E2E_SHOTS") or tmp_path / "shots")   # CI keeps them; design shots: web/tests/shots.mjs
    shots.mkdir(parents=True, exist_ok=True)
    # CI's runner has no Inter: system-ui falls to DejaVu Sans, which is wider. Force it so a local run matches CI.
    conf = tmp_path / "fonts.conf"
    conf.write_text('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><include ignore_missing="yes">/etc/fonts/fonts.conf</include>'
                    + "".join(f'<match target="pattern"><test name="family"><string>{f}</string></test><edit name="family" mode="assign" binding="strong"><string>DejaVu Sans</string></edit></match>'
                              for f in ("system-ui", "sans-serif")) + "</fontconfig>")
    run = subprocess.run(["node", str(ROOT / "web" / "tests" / "e2e.mjs"), str(tmp_path / "site"), str(shots)],
                         capture_output=True, text=True, env={**os.environ, "FONTCONFIG_FILE": str(conf)})
    assert run.returncode == 0, run.stdout[-2000:] + run.stderr[-2000:]
