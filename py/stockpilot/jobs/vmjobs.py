"""The VM job runner: cloud sessions ask for work by pushing `jobs/<id>.json` to branch `vm-jobs`; this runs on the VM as a
oneshot systemd timer, does each request that has no `results/<id>.json`, one at a time, and pushes the results back.

A fixed allow-list of jobs (anything else is `rejected`). Args are checked against a schema per job, and every command is an
argument list, never a shell string. Job files count only from commits whose author is in `ops/vm-jobs/allowed_requesters.txt`
of the VM's own checkout (never the one on the vm-jobs branch). Secrets are scrubbed from every log line. It never places orders."""
import fcntl
import json
import os
import re
import shutil
import subprocess
import urllib.request
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

BRANCH = "vm-jobs"
IST = timezone(timedelta(hours=5, minutes=30))
WINDOW = ((9, 0), (17, 0))                       # 09:00 to 17:00 IST, both ends included
PROJECT = "stockpilotgn"
SNAPSHOT_TAG, SNAPSHOT_KEY = "market-snapshot", "SNAPSHOT_AGE_RECIPIENT"
TAIL = 200
ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
HIDDEN = "[hidden]"
PATTERNS = [re.compile(p) for p in (
    r"AGE-SECRET-KEY-1[A-Z0-9]+", r"sk-ant-[A-Za-z0-9_-]+", r"gh[pousr]_[A-Za-z0-9]{20,}", r"github_pat_[A-Za-z0-9_]+",
    r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+", r"(?i)\b(?:token|secret|password|passwd|api[_-]?key)\s*[=:]\s*\S+")]


class Busy(Exception):
    """Another runner holds the lock."""


@contextmanager
def locked(path: Path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as err:
            raise Busy() from err
        yield


def read_env(path: Path) -> dict:
    out = {}
    try:
        for line in Path(path).read_text().splitlines():
            if "=" in line and not line.lstrip().startswith("#"):
                key, _, value = line.partition("=")
                out[key.strip()] = value.strip().strip("'\"")
    except OSError:
        pass
    return out


def scrub(text: str, secrets=()) -> str:
    for secret in sorted(secrets, key=len, reverse=True):
        text = text.replace(secret, HIDDEN)
    for pattern in PATTERNS:
        text = pattern.sub(HIDDEN, text)
    return text


def default_run(argv, cwd=None, env=None, keep=2000):
    """Run one command, merging stderr into stdout, keeping only the last `keep` lines in memory (the VM has 1 GB)."""
    proc = subprocess.Popen(argv, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    lines = deque(maxlen=keep)
    for line in proc.stdout:
        lines.append(line.rstrip("\n"))
    return proc.wait(), "\n".join(lines)


def default_http_ok(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:        # noqa: S310 - a fixed https URL
            return resp.status == 200
    except Exception:  # noqa: BLE001
        return False


# ---- the allow-list and its argument schemas ------------------------------------------------------------------

def _day(value) -> str:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        raise ValueError("date must look like 2026-11-24")
    date.fromisoformat(value)
    return value


SCHEMAS = {          # job -> {arg: validator}; every arg is optional
    "build-site": {}, "verify": {}, "deploy": {}, "snapshot-publish": {}, "decide-refresh": {"date": _day},
}


def validate(job, args) -> dict:
    if job not in SCHEMAS:
        raise ValueError(f"'{job}' is not an allowed job (allowed: {', '.join(sorted(SCHEMAS))})")
    if not isinstance(args, dict):
        raise ValueError("args must be an object")
    schema = SCHEMAS[job]
    extra = sorted(set(args) - set(schema))
    if extra:
        raise ValueError(f"unknown args for {job}: {', '.join(map(str, extra))}")
    return {key: schema[key](value) for key, value in args.items()}


# ---- one job's context and the jobs ---------------------------------------------------------------------------

class Failed(Exception):
    def __init__(self, code=1, note=""):
        super().__init__(note)
        self.code, self.note = code, note


@dataclass
class Ctx:
    runner: "Runner"
    log: deque = field(default_factory=lambda: deque(maxlen=TAIL * 2))
    outputs: dict = field(default_factory=dict)
    planned: list = field(default_factory=list)

    def sh(self, argv, *, cwd=None, env=None) -> tuple[int, str]:
        """Run one command (an argument list); in a dry run only note it."""
        assert isinstance(argv, list) and all(isinstance(a, str) for a in argv)
        self.log.append("$ " + " ".join(argv))
        if self.runner.dry_run:
            self.planned.append(" ".join(argv))
            return 0, ""
        code, out = self.runner.run(argv, cwd=cwd, env=env or self.runner.base_env())
        self.log.extend(out.splitlines())
        return code, out

    def sp(self, *args, env=None):
        return self.sh([*self.runner.sp, *args], cwd=self.runner.root, env=env)

    def must(self, argv_result, what):
        code, _ = argv_result
        if code != 0:
            raise Failed(code, f"{what} exited {code}")


def job_build_site(ctx, args):
    ctx.must(ctx.sp("build-site"), "sp build-site")


def build_verified(ctx) -> int:
    """The deploy order: build, verify (writes the price flags; not the gate), rebuild, verify (the gate). Returns the gate's exit."""
    ctx.must(ctx.sp("build-site"), "sp build-site")
    ctx.sp("verify")
    ctx.must(ctx.sp("build-site"), "sp build-site (second)")
    code, _ = ctx.sp("verify")
    ctx.outputs["gate_exit"] = code
    return code


def job_verify(ctx, args):
    if build_verified(ctx) != 0:
        raise Failed(ctx.outputs["gate_exit"], "the second sp verify failed (the gate)")


def _ids(text: str) -> list[str]:
    try:
        data = json.loads(text)
    except ValueError:
        return []
    rows = data if isinstance(data, list) else []
    return [str(r.get("Id") or r.get("id") or r.get("deployment_id")) for r in rows if isinstance(r, dict) and (r.get("Id") or r.get("id") or r.get("deployment_id"))]


def job_deploy(ctx, args):
    r = ctx.runner
    ctx.outputs["deployed"] = False
    on = ctx.sh(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=r.root)
    if not r.dry_run and on[1].strip() != "stage-1-skeleton":
        raise Failed(1, f"the VM checkout is on '{on[1].strip()}', not stage-1-skeleton")
    ctx.must(ctx.sh(["git", "fetch", "origin"], cwd=r.root), "git fetch")
    ctx.must(ctx.sh(["git", "merge", "--ff-only", "origin/stage-1-skeleton"], cwd=r.root), "git merge --ff-only origin/stage-1-skeleton")
    if build_verified(ctx) != 0:
        raise Failed(ctx.outputs["gate_exit"], "the gate failed (second sp verify): not deployed")
    web = r.root / "web"
    listing = [r.wrangler, "pages", "deployment", "list", "--project-name", PROJECT, "--json"]
    before = _ids(ctx.sh(listing, cwd=web)[1])
    code, out = ctx.sh([r.wrangler, "pages", "deploy", "../site", "--project-name", PROJECT, "--branch", "main"], cwd=web)
    if code != 0:
        raise Failed(code, "wrangler pages deploy failed")
    ids = _ids(ctx.sh(listing, cwd=web)[1])
    found = re.search(rf"https://([0-9a-f]{{8}})\.{PROJECT}\.pages\.dev", out)
    new = ids[0] if ids else (found.group(1) if found else None)
    ctx.outputs.update(deployed=True, deployment_id=new)
    ctx.outputs["rollback_to"] = next((i for i in before + ids if i != new), None)
    if not r.dry_run and not r.http_ok(f"https://{PROJECT}.pages.dev/"):
        raise Failed(1, f"the live site did not load after deploy; promote {ctx.outputs['rollback_to']} again")
    pushed = ctx.sh(["git", "push", "origin", "HEAD:refs/heads/main"], cwd=r.root)     # never forced: only a fast-forward goes
    ctx.outputs["main"] = "fast-forwarded" if pushed[0] == 0 else "refused (not a fast-forward)"
    if pushed[0] != 0:
        raise Failed(pushed[0], "deployed, but main could not be fast-forwarded")


def job_snapshot_publish(ctx, args):
    ctx.must(ctx.sp("backup", "market", "--tag", SNAPSHOT_TAG, "--recipient-env", SNAPSHOT_KEY), "sp backup market")
    ctx.outputs["tag"] = SNAPSHOT_TAG


def job_decide_refresh(ctx, args):
    """The supported decide path (lane N): `sp daily`, forced. It gathers, makes the day's calls with the Claude runner (setup
    token only), then ships. One run."""
    env = ctx.runner.base_env()
    env["CLAUDE_CODE_OAUTH_TOKEN"] = ctx.runner.env_file.get("CLAUDE_CODE_OAUTH_TOKEN", "")
    ctx.must(ctx.sp("daily", *(["--date", args["date"]] if "date" in args else []), env=env), "sp daily")


JOBS = {"build-site": job_build_site, "verify": job_verify, "deploy": job_deploy,
        "snapshot-publish": job_snapshot_publish, "decide-refresh": job_decide_refresh}
assert set(JOBS) == set(SCHEMAS)


# ---- the runner -----------------------------------------------------------------------------------------------

class Runner:
    def __init__(self, root, queue, *, sp, wrangler, run=default_run, now=None, dry_run=False, http_ok=default_http_ok):
        self.root, self.queue = Path(root), Path(queue)
        self.sp, self.wrangler, self.run, self.dry_run, self.http_ok = list(sp), wrangler, run, dry_run, http_ok
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.env_file = read_env(self.root / ".env")

    # -- environment and secrets
    def secrets(self) -> list[str]:
        return [v for v in self.env_file.values() if len(v) >= 8]

    def base_env(self) -> dict:
        """A small environment: no inherited API keys; the setup token only where a job asks for it."""
        keep = {k: v for k, v in os.environ.items() if k in ("PATH", "HOME", "LANG", "LC_ALL", "USER", "TZ", "WRANGLER")}
        keep["PATH"] = f"{Path(self.wrangler).parent}:{keep.get('PATH', '/usr/bin:/bin')}"
        return keep

    def git(self, *argv, cwd=None):
        return self.run(["git", *argv], cwd=cwd or self.queue, env=self.base_env())

    # -- window, allow-list, queue
    def in_window(self) -> bool:
        t = self.now().astimezone(IST)
        return WINDOW[0] <= (t.hour, t.minute) <= WINDOW[1]

    def allowed(self) -> set[str]:
        try:
            lines = (self.root / "ops/vm-jobs/allowed_requesters.txt").read_text().splitlines()
        except OSError:
            return set()
        return {l.strip().lower() for l in lines if l.strip() and not l.lstrip().startswith("#")}

    def sync(self) -> bool:
        """Fetch vm-jobs into the queue clone and reset to it. False when the branch is not there."""
        if not (self.queue / ".git").exists():
            self.queue.mkdir(parents=True, exist_ok=True)
            url = self.git("remote", "get-url", "origin", cwd=self.root)[1].strip()
            self.git("init", "-q")
            self.git("remote", "add", "origin", url)
            self.git("config", "user.name", "sp-vm-jobs")
            self.git("config", "user.email", "sp-vm-jobs@localhost")
        if self.git("fetch", "-q", "origin", f"+{BRANCH}:refs/remotes/origin/{BRANCH}")[0] != 0:
            return False
        return self.git("checkout", "-q", "-f", "-B", BRANCH, f"origin/{BRANCH}")[0] == 0 and self.git("clean", "-fdq")[0] == 0

    def requested(self) -> list[str]:
        """Job ids with no result yet, oldest request first."""
        jobs = self.queue / "jobs"
        done = {p.stem for p in (self.queue / "results").glob("*.json")} if (self.queue / "results").exists() else set()
        have = [p.stem for p in jobs.glob("*.json") if ID_RE.fullmatch(p.stem)] if jobs.exists() else []
        log = self.git("log", "--reverse", "--diff-filter=A", "--name-only", "--format=", "--", "jobs")[1].split()
        order = [Path(n).stem for n in log if n.startswith("jobs/") and n.endswith(".json")]
        pending = [i for i in have if i not in done]
        return sorted(pending, key=lambda i: (order.index(i) if i in order else len(order), i))

    def authors(self, id) -> set[str]:
        out = self.git("log", "--format=%ae", "--", f"jobs/{id}.json")[1]
        return {a.strip().lower() for a in out.splitlines() if a.strip()}

    # -- one request
    def vet(self, id):
        """The spec if the request is acceptable, else raises ValueError with the reason."""
        bad = self.authors(id) - self.allowed()
        if bad or not self.authors(id):
            raise ValueError("author is not in ops/vm-jobs/allowed_requesters.txt: the job file is not accepted")
        try:
            spec = json.loads((self.queue / "jobs" / f"{id}.json").read_text())
        except ValueError as err:
            raise ValueError(f"the job file is not valid JSON ({err.__class__.__name__})") from err
        if not isinstance(spec, dict) or spec.get("id") != id:
            raise ValueError("the id inside the job file does not match its file name")
        return spec["job"] if isinstance(spec.get("job"), str) else None, validate(spec.get("job"), spec.get("args", {}))

    def execute(self, id) -> dict:
        started = self.now().isoformat()
        ctx = Ctx(self)
        try:
            job, args = self.vet(id)
        except (ValueError, KeyError) as err:
            return self.result(id, "rejected", started, None, [str(err)], {})
        status, code = "ok", 0
        try:
            JOBS[job](ctx, args)
        except Failed as err:
            status, code = "failed", err.code
            ctx.log.append(err.note)
        except Exception as err:  # noqa: BLE001 - a crash is a failed job, not a dead runner
            status, code = "failed", 1
            ctx.log.append(f"{err.__class__.__name__}: {err}")
        res = self.result(id, "dry-run" if self.dry_run and status == "ok" else status, started, code, list(ctx.log), ctx.outputs)
        if self.dry_run:
            res["would_run"] = ctx.planned
        return res

    def result(self, id, status, started, code, lines, outputs) -> dict:
        secrets = self.secrets()
        tail = [scrub(l, secrets) for l in lines][-TAIL:]
        clean = json.loads(scrub(json.dumps(outputs), secrets)) if outputs else {}
        return {"id": id, "status": status, "started": started, "finished": self.now().isoformat(), "exit": code,
                "log_tail": tail, "outputs": clean}

    def publish(self, res) -> None:
        path = self.queue / "results" / f"{res['id']}.json"
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(res, indent=1) + "\n")
        self.git("add", f"results/{res['id']}.json")
        self.git("commit", "-q", "-m", f"result {res['id']}: {res['status']}")
        if self.git("push", "-q", "origin", BRANCH)[0] != 0:
            self.git("pull", "-q", "--rebase", "origin", BRANCH)
            self.git("push", "-q", "origin", BRANCH)

    def poll(self) -> list[dict]:
        """One timer firing: nothing outside the window, nothing while another runner is busy, else every pending job in order."""
        if not self.in_window():
            return []
        try:
            with locked(self.queue.parent / "vm-jobs.lock"):
                if not self.sync():
                    return []
                done = []
                for id in self.requested():
                    res = self.execute(id)
                    done.append(res)
                    if not self.dry_run:
                        self.publish(res)
                return done
        except Busy:
            return []
