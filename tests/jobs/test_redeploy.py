"""The v2 redeploy (issue #113): what sp-tick's ship step did for the site, as a timer of its own. It deploys at the two daily
slots and whenever the shipped paths changed on main; it only ever fast-forwards its checkout; a failed deploy leaves the
live site as it was and shows as a problem; the hard blocks and the rollback live in scripts/cutover (their own tests)."""
import json
from datetime import datetime, timedelta, timezone

import pytest

from fakes import make_machine
from stockpilot.jobs import redeploy, ship

IST = timezone(timedelta(hours=5, minutes=30))


def ist(day, hour, minute=0):
    return datetime(2026, 11, day, hour, minute, tzinfo=IST)


class Git:
    """Answers the few git questions redeploy asks; `tree` is what HEAD holds under the shipped paths."""

    def __init__(self, tree="t1", remote_tree=None, branch="main", dirty="", ff_fails=False):
        self.tree, self.remote_tree, self.branch, self.dirty, self.ff_fails, self.calls = tree, remote_tree or tree, branch, dirty, ff_fails, []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("rev-parse", "--abbrev-ref"):
            return self.branch + "\n"
        if args[0] == "status":
            self.status_args = args
            specs = args[args.index("--") + 1:] if "--" in args else ()      # like git: only the named paths are looked at
            return "".join(l + "\n" for l in self.dirty.splitlines() if not specs or l[3:].split("/")[0] in specs)
        if args[0] == "merge":
            if self.ff_fails:
                raise RuntimeError("Not possible to fast-forward")
            self.tree = self.remote_tree
            return ""
        if args[0] == "rev-parse":
            return "\n".join(f"{self.tree}-{p}" for p in args[1:]) + "\n"
        return ""


def machine(tmp_path, now, git=None, deploy=None, **kw):
    log = []
    m = make_machine(tmp_path, now=now.replace(tzinfo=None), git=git or Git(),
                     deploy=deploy or (lambda: log.append("deploy") or "Dashboard deployed."), **kw)
    m.log = log
    return m


def built(log):
    return lambda m, db, now: log.append("build") or None


def problems(m):
    with m.db("t") as db:
        return db.execute("select severity, message from problems where job = 'redeploy' and resolution is null").fetchall()


def test_the_first_run_after_a_slot_builds_and_deploys(tmp_path):
    m = machine(tmp_path, ist(26, 8))
    out = redeploy.run(m, ist(26, 8), build=built(m.log))
    assert m.log == ["build", "deploy"] and out["status"] == "deployed" and out["reason"] == "daily"


def test_nothing_due_between_slots_exits_without_building(tmp_path):
    m = machine(tmp_path, ist(26, 8))
    redeploy.run(m, ist(26, 8), build=built(m.log))
    m.log.clear()
    out = redeploy.run(m, ist(26, 9), build=built(m.log))
    assert m.log == [] and out["status"] == "idle"


def test_the_late_slot_ships_the_nights_public_files(tmp_path):
    m = machine(tmp_path, ist(26, 8))
    redeploy.run(m, ist(26, 8), build=built(m.log))
    m.log.clear()
    assert redeploy.run(m, ist(26, 23, 40), build=built(m.log))["reason"] == "daily"
    assert m.log == ["build", "deploy"]


def test_a_web_change_on_main_deploys_at_once_and_the_checkout_fast_forwards(tmp_path):
    git = Git(tree="t1", remote_tree="t2")
    m = machine(tmp_path, ist(26, 8), git=git)
    git.remote_tree = "t1"
    redeploy.run(m, ist(26, 8), build=built(m.log))
    m.log.clear()
    git.remote_tree = "t2"
    out = redeploy.run(m, ist(26, 9), build=built(m.log))
    assert out["status"] == "deployed" and out["reason"] == "changed"
    assert ("merge", "--ff-only", "origin/main") in git.calls and ("fetch", "--quiet", "origin", "main") in git.calls
    assert all(c[0] not in ("reset", "checkout", "pull", "rebase") for c in git.calls)


def test_a_change_outside_the_shipped_paths_does_not_deploy(tmp_path):
    git = Git()
    m = machine(tmp_path, ist(26, 8), git=git)
    redeploy.run(m, ist(26, 8), build=built(m.log))
    m.log.clear()
    assert redeploy.run(m, ist(26, 9), build=built(m.log))["status"] == "idle"
    asked = [c for c in git.calls if c[0] == "rev-parse" and c[1] != "--abbrev-ref"][-1]
    assert "HEAD:web" in asked


def test_a_dirty_or_off_main_checkout_is_not_touched_and_is_a_problem(tmp_path):
    for git in (Git(branch="lane/x"), Git(dirty=" M web/app.js\n")):
        m = machine(tmp_path / git.branch.replace("/", "_") / str(bool(git.dirty)), ist(26, 8), git=git)
        out = redeploy.run(m, ist(26, 8), build=built(m.log))
        assert not any(c[0] == "merge" for c in git.calls)
        assert out["status"] == "held" and m.log == []
        assert any("checkout" in msg for _, msg in problems(m))


def test_a_checkout_that_cannot_fast_forward_holds_the_deploy(tmp_path):
    git = Git(ff_fails=True)
    m = machine(tmp_path, ist(26, 8), git=git)
    out = redeploy.run(m, ist(26, 8), build=built(m.log))
    assert out["status"] == "held" and m.log == []
    assert any("fast-forward" in msg for _, msg in problems(m))


def test_a_failed_deploy_is_a_problem_and_marks_nothing_as_deployed(tmp_path):
    def broken():
        raise RuntimeError("deploy failed: hard block js_page_error; rolled back")
    m = machine(tmp_path, ist(26, 8), deploy=broken)
    out = redeploy.run(m, ist(26, 8), build=built(m.log))
    assert out["status"] == "failed" and "js_page_error" in out["error"]
    assert any(sev == "error" and "js_page_error" in msg for sev, msg in problems(m))
    assert not (m.root / redeploy.STATE).exists() or json.loads((m.root / redeploy.STATE).read_text()).get("ok") is None


def test_a_failed_deploy_is_not_retried_in_a_tight_loop_but_is_after_two_hours(tmp_path):
    calls = []
    def broken():
        calls.append(1)
        raise RuntimeError("deploy failed")
    m = machine(tmp_path, ist(26, 8), deploy=broken)
    redeploy.run(m, ist(26, 8), build=built(m.log))
    assert redeploy.run(m, ist(26, 8, 30), build=built(m.log))["status"] == "backoff" and len(calls) == 1
    redeploy.run(m, ist(26, 10, 5), build=built(m.log))
    assert len(calls) == 2


def test_a_good_deploy_after_a_failure_clears_the_problem(tmp_path):
    state = {"fail": True}
    def flaky():
        if state["fail"]:
            raise RuntimeError("deploy failed")
        return "Dashboard deployed."
    m = machine(tmp_path, ist(26, 8), deploy=flaky)
    redeploy.run(m, ist(26, 8), build=built(m.log))
    assert problems(m)
    state["fail"] = False
    assert redeploy.run(m, ist(26, 10, 5), build=built(m.log))["status"] == "deployed"
    assert problems(m) == []


def test_a_build_that_fails_does_not_deploy(tmp_path):
    def bad_build(m, db, now):
        raise RuntimeError("no data yet")
    m = machine(tmp_path, ist(26, 8))
    out = redeploy.run(m, ist(26, 8), build=bad_build)
    assert out["status"] == "failed" and m.log == []


# ---- deploy_safe: the daily ship and this timer deploy through scripts/cutover, never bare wrangler ----

class Done:
    def __init__(self, code, out="", err=""):
        self.returncode, self.stdout, self.stderr = code, out, err


def test_deploy_safe_runs_the_cutover_script_on_production(tmp_path):
    m = make_machine(tmp_path)
    seen = []
    def run(cmd, **kw):
        seen.append((cmd, kw.get("cwd")))
        return Done(0, 'Deployed to https://x.pages.dev. Checking the four hard blocks.\n{"ok":true,"url":"https://x.pages.dev","rolledBack":false}\n')
    assert ship.deploy_safe(m.cfg, run=run, node="/usr/bin/node", wrangler="/usr/bin/wrangler") == "Dashboard deployed."
    cmd, cwd = seen[0]
    assert cmd[:2] == ["/usr/bin/node", str(m.root / "scripts" / "cutover" / "cutover.mjs")] and cmd[2:] == ["deploy", "--target", "production"]


def test_deploy_safe_raises_with_the_failed_blocks_and_says_whether_it_rolled_back(tmp_path):
    m = make_machine(tmp_path)
    line = '{"ok":false,"url":"https://x.pages.dev","failed":["js_page_error"],"rolledBack":true,"liveAfterRollback":true}'
    with pytest.raises(RuntimeError) as err:
        ship.deploy_safe(m.cfg, run=lambda cmd, **kw: Done(1, line + "\n"), node="node", wrangler="/usr/bin/wrangler")
    assert "js_page_error" in str(err.value) and "rolled back" in str(err.value)


def test_deploy_safe_names_a_preflight_gap_and_a_failed_rollback(tmp_path):
    m = make_machine(tmp_path)
    with pytest.raises(RuntimeError) as err:
        ship.deploy_safe(m.cfg, run=lambda cmd, **kw: Done(3, "missing: SP_COOKIE_KEY\n"), node="node", wrangler="/usr/bin/wrangler")
    assert "preflight" in str(err.value) and "SP_COOKIE_KEY" in str(err.value)
    bad = '{"ok":false,"failed":["page_loads"],"rolledBack":false,"error":"rollback failed: x"}'
    with pytest.raises(RuntimeError) as err:
        ship.deploy_safe(m.cfg, run=lambda cmd, **kw: Done(1, bad), node="node", wrangler="/usr/bin/wrangler")
    assert "NOT rolled back" in str(err.value)


def test_a_busy_store_is_not_a_failure(tmp_path):
    from stockpilot import store
    def busy(m, db, now):
        raise store.Busy({"job": "daily", "pid": 1, "since": "x"})
    m = machine(tmp_path, ist(26, 8))
    out = redeploy.run(m, ist(26, 8), build=busy)
    assert out["status"] == "busy" and redeploy.exit_code(out) == 75 and m.log == [] and problems(m) == []


def test_a_site_over_the_pages_file_limit_is_not_deployed(tmp_path):
    def huge(m, db, now):
        site = m.root / "site"
        site.mkdir(parents=True, exist_ok=True)
        for n in range(redeploy.MAX_FILES + 1):
            (site / f"f{n}.json").write_text("")
        return None
    m = machine(tmp_path, ist(26, 8))
    out = redeploy.run(m, ist(26, 8), build=huge)
    assert out["status"] == "failed" and "20,000" in out["error"] and m.log == []
    assert any("20,000" in msg for _, msg in problems(m))


def test_a_modified_verify_report_does_not_hold_the_deploy_but_a_shipped_path_does(tmp_path):
    git = Git(dirty=" M docs/status/verify-2026-11-26.md\n")      # sp verify writes this on the VM, every evening
    m = machine(tmp_path / "a", ist(26, 8), git=git)
    assert redeploy.run(m, ist(26, 8), build=built(m.log))["status"] == "deployed"
    assert git.status_args[-len(redeploy.RUN_PATHS) - 1:] == ("--",) + redeploy.RUN_PATHS
    for path in redeploy.RUN_PATHS:
        assert path.split("/")[0] in ("web", "src", "config", "scripts", "ops")


def test_a_hard_verify_failure_blocks_the_deploy_like_the_evening_ship(tmp_path):
    def blocked(m, db, now):
        return {"hard_failed": 1, "summary": "check 3 failed"}
    m = machine(tmp_path, ist(26, 23, 40))
    out = redeploy.run(m, ist(26, 23, 40), build=blocked)
    assert out["status"] == "failed" and "sp verify" in out["error"] and m.log == []
    assert any("sp verify" in msg for _, msg in problems(m))


def test_the_default_build_is_the_verified_build_the_evening_ship_uses(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(ship, "build_verified", lambda m, db, day, now=None: seen.append(day) or ({"as_of": "x"}, {"hard_failed": 0, "summary": ""}))
    m = machine(tmp_path, ist(26, 8))
    assert redeploy.run(m, ist(26, 8))["status"] == "deployed" and seen


def test_the_site_lock_is_shared_by_the_evening_ship_and_the_redeploy(tmp_path):
    from stockpilot import store
    m = machine(tmp_path, ist(26, 8))
    with ship.site_lock(m.root):
        out = redeploy.run(m, ist(26, 8), build=built(m.log))
        assert out["status"] == "busy" and redeploy.exit_code(out) == 75 and m.log == []
        with pytest.raises(store.Busy):
            with ship.site_lock(m.root):
                pass
    assert redeploy.run(m, ist(26, 8), build=built(m.log))["status"] == "deployed"
