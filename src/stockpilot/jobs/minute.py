"""The one-minute check (ticket V1): runs as a systemd oneshot timer, never as a daemon.

One firing: ask the job source for queued work (one cheap read; nothing queued means exit at once), hand each model job to
`JobRunner` with a fallback `Chain`, start GitHub jobs through the injected `start_github`, and raise the stale-pipeline
alarm through the injected `alarm`. Model order: forecasts Sonnet then Gemini, then a plain "usage is used up" message;
tagging and reading feedback Gemini account A, then B, then Haiku. All I/O is injected, so tests use fakes and spend nothing."""
import subprocess
import tempfile
from datetime import datetime, timedelta

from stockpilot.jobrun import CONTRACT, IST, JobFailed, JobRunner
from stockpilot.jobs import wire

QUOTA = "Usage is used up. Try again in about an hour."
QUOTA_BN = "ব্যবহারের সীমা শেষ। প্রায় এক ঘণ্টা পরে আবার চেষ্টা করুন।"

FORECAST = ("sonnet", "gemini-a")
TAGGING = ("gemini-a", "gemini-b", "haiku")
CHAINS = {"analyse": FORECAST, "refresh_call": FORECAST, "weekly_review": FORECAST,
          "news_tag": TAGGING, "feedback_read": TAGGING}
REFUSAL_WORDS = ("usage limit", "rate limit", "quota", "limit reached", "resource_exhausted", "exhausted", "429", "overloaded")


class NotWired(Exception):
    """No GitHub workflow exists for this job kind yet; the job stays queued until one does."""


class Refused(Exception):
    """A model said no for quota or load reasons; the chain moves on."""


class Chain:
    """Ask each backend in order; the first answer wins. A refusal moves on; when all refuse the job fails in plain words."""

    def __init__(self, backends):
        self.backends, self.used = backends, None

    def ask(self, prompt):
        for backend in self.backends:
            try:
                answer = backend.ask(prompt)
            except Refused:
                continue
            self.used = backend.name
            return answer
        raise JobFailed(QUOTA, QUOTA_BN)


def chain_for(kind: str, make, payload: dict | None = None) -> Chain:
    """`make(name)` builds one backend by name; the chain for a kind is fixed here. A refresh the news planner marked medium
    (`reason` news_medium) takes the cheap chain, as decided (round 4): Gemini, then Haiku."""
    names = TAGGING if kind == "refresh_call" and (payload or {}).get("reason") == "news_medium" else CHAINS[kind]
    return Chain([make(name) for name in names])


class CliBackend:
    """One model through its command line, in an empty folder, prompt on stdin. A quota or load message is a `Refused`."""
    MODELS = {"sonnet": ["claude", "-p", "--model", "sonnet"], "haiku": ["claude", "-p", "--model", "haiku"],
              "gemini-a": ["agy", "-p"], "gemini-b": ["agy", "-p"]}

    def __init__(self, name, env=None, run=subprocess.run, timeout=290):
        self.name, self.env, self.run, self.timeout = name, env or {}, run, timeout

    def ask(self, prompt):
        with tempfile.TemporaryDirectory(prefix="sp-min-") as empty:
            try:
                done = self.run(self.MODELS[self.name], cwd=empty, env=self.env, input=prompt, capture_output=True, text=True,
                                timeout=self.timeout)
            except subprocess.TimeoutExpired as err:
                raise Refused(self.name) from err
            except OSError as err:
                raise Refused(self.name) from err
        text = (done.stdout or "") + (done.stderr or "")
        if done.returncode != 0:
            if any(w in text.lower() for w in REFUSAL_WORDS):
                raise Refused(self.name)
            raise RuntimeError(f"{self.name} exited {done.returncode}")
        return done.stdout.strip()


GITHUB_FAIL = "Could not start this on GitHub. The owner has been told."
STALE_AFTER = timedelta(hours=26)
ALARM_EVERY = timedelta(hours=6)
STALE_TEXT = "The nightly market job has not finished in over a day. Numbers on the site may be old."


def ask_handler(template: str):
    """A model job's handler: fill the prompt from the payload, ask the chain, return its answer."""
    def handler(ctx):
        ctx.progress("Asking the model")
        return ctx.model.ask(template.format(**ctx.payload))
    return handler


def _stale(last_nightly, now, state) -> bool:
    if not last_nightly or now - datetime.fromisoformat(last_nightly) < STALE_AFTER:
        return False
    last = state.get("last_alarm")
    return not last or now - datetime.fromisoformat(last) >= ALARM_EVERY


def tick(source, sink, *, make_backend, handlers, start_github, alarm, state, now, budget_s=240, enqueue=None,
         check_github=None) -> dict:
    """One firing. `source.pending()` is the only read when nothing is happening:
    `{"queued": [rows], "last_nightly": time or None}` plus, when the source has them, `running_github` (started GitHub jobs to
    check), `last_weekly`, `untagged` (a count) and `open_kinds`. A job whose kind has no handler stays queued for whoever owns it."""
    started = now()
    seen = source.pending()
    ran = began = 0
    finished = 0
    tagged = False
    for row in seen.get("running_github") or ():
        finished += _finish_github(sink, row, check_github, now)
    for row in seen["queued"]:
        runs_on = CONTRACT["job_kinds"].get(row["kind"], {}).get("runs_on")
        if runs_on == "github_public":
            began += _start_github(sink, row, start_github, now)
        elif runs_on in ("vm_model", "vm_private") and row["kind"] in handlers and now() - started < timedelta(seconds=budget_s):
            _adopt(sink, row)
            runner = JobRunner(sink, model=chain_for(row["kind"], make_backend, row["payload"]) if row["kind"] in CHAINS else None, clock=now)
            runner.register(row["kind"], handlers[row["kind"]])
            runner.run(row["id"])
            ran += 1
            tagged = tagged or (row["kind"] == "news_tag" and sink.jobs[row["id"]]["status"] == "done")
    made = []
    if enqueue is not None:
        made = wire.schedule(seen, source, enqueue, started, ran_tag=tagged)
    raised = _stale(seen.get("last_nightly"), started, state)
    if raised:
        alarm(STALE_TEXT)
        state["last_alarm"] = started.isoformat()
    return {"ran": ran, "started": began, "alarm": raised, **({"finished": finished} if finished else {}),
            **({"enqueued": made} if made else {})}


def _adopt(sink, row):
    if row["id"] not in sink.jobs:
        sink.create_job(row)


def _finish_github(sink, row, check_github, now) -> int:
    """A GitHub job that was started: when its run has finished, close the job (done or failed) in plain words."""
    if check_github is None:
        return 0
    verdict = check_github(row)
    if verdict is None:
        return 0
    row = dict(row)
    nlines = int(row.pop("nlines", 0) or 0)
    sink.jobs[row["id"]] = row                                    # already running in D1; the cache learns it, nothing is rewritten
    sink.lines[row["id"]] = [{}] * nlines
    sink.history[row["id"]] = ["queued", "running"]
    stamp = now().astimezone(IST).replace(microsecond=0).isoformat()
    ok = verdict == "success"
    text = "Finished on GitHub" if ok else GITHUB_FAIL
    sink.append_line({"job_id": row["id"], "seq": len(sink.lines[row["id"]]) + 1, "at": stamp, "state": "ok" if ok else "fail",
                      "text": "Done" if ok else text, "text_bn": None if ok else "গিটহাবে কাজটি শুরু করা যায়নি। মালিককে জানানো হয়েছে।"})
    if ok:
        sink.update_job(row["id"], status="done", result="Done", finished_at=stamp)
    else:
        sink.update_job(row["id"], status="failed", error=text, error_bn="গিটহাবে কাজটি শেষ হয়নি। মালিককে জানানো হয়েছে।", finished_at=stamp)
    return 1


def _start_github(sink, row, start_github, now) -> int:
    _adopt(sink, row)
    stamp = now().astimezone(IST).replace(microsecond=0).isoformat()
    try:
        start_github(row)
    except NotWired:
        sink.jobs.pop(row["id"]); sink.lines.pop(row["id"]); sink.history.pop(row["id"])
        return 0
    except Exception:  # noqa: BLE001 - the reason stays in the VM log, never on the page
        sink.append_line({"job_id": row["id"], "seq": 1, "at": stamp, "state": "fail", "text": GITHUB_FAIL, "text_bn": None})
        sink.update_job(row["id"], status="failed", error=GITHUB_FAIL, finished_at=stamp)
        return 0
    sink.append_line({"job_id": row["id"], "seq": 1, "at": stamp, "state": "info", "text": "Started on GitHub", "text_bn": None})
    sink.update_job(row["id"], status="running", started_at=stamp)
    return 1


# ---- D1 over HTTP (stdlib only: an idle firing must stay far under 20 MB) ----------------------------------------
_COLS = "id, kind, payload, asked_by, status, result, error, error_bn, created_at, started_at, finished_at"
GITHUB_KINDS = tuple(k for k, v in CONTRACT["job_kinds"].items() if v["runs_on"] == "github_public")
_KINDS_SQL = ",".join(f"'{k}'" for k in GITHUB_KINDS)
_NULLS = ", ".join(["null"] * 11)
PENDING_SQL = (f"select {_COLS}, (select count(*) from job_lines where job_id = jobs.id) as nlines, null as last_nightly, "
               f"null as last_weekly, null as untagged, null as open_kinds from jobs "
               f"where status = 'queued' or (status = 'running' and kind in ({_KINDS_SQL})) "
               f"union all select {_NULLS}, null, "
               f"(select max(finished_at) from jobs where kind = 'nightly' and status = 'done'), "
               f"(select max(created_at) from jobs where kind = 'weekly_review'), "
               f"(select count(*) from news_items where tagged_at is null), "
               f"(select group_concat(distinct kind) from jobs where status in ('queued', 'running') and kind in ('news_tag', 'news_rank')) "
               f"order by created_at")


def cloudflare_query(account: str, database: str, token: str, post=None):
    """`query(sql, params) -> rows` over Cloudflare's D1 HTTP API. `post(url, headers, body) -> dict` is injectable."""
    url = f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{database}/query"
    post = post or _post_json

    def query(sql, params=()):
        out = post(url, {"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                   {"sql": sql, "params": list(params)})
        if not out.get("success"):
            raise RuntimeError("D1 query failed: " + "; ".join(e.get("message", "?") for e in out.get("errors", [])))
        return out["result"][0].get("results", [])
    return query


def _post_json(url, headers, body):
    import json
    import urllib.request
    req = urllib.request.Request(url, json.dumps(body).encode(), headers, method="POST")
    with urllib.request.urlopen(req, timeout=20) as resp:  # noqa: S310 - fixed https URL
        return json.loads(resp.read())


class D1Db:
    """Just enough of a sqlite connection for `SqliteSink`: every execute is one HTTP query, so commit does nothing."""

    def __init__(self, query):
        self.query = query

    def execute(self, sql, params=()):
        return self.query(sql, params)

    def commit(self):
        pass


class D1Source:
    """`pending()` is one query: the queued jobs (and started GitHub jobs) oldest first, plus the facts the schedule needs."""

    def __init__(self, query):
        self.query = query

    def pending(self) -> dict:
        import json
        rows = self.query(PENDING_SQL)
        jobs = [{**{k: v for k, v in r.items() if k not in ("last_nightly", "last_weekly", "untagged", "open_kinds")
                    and (k != "nlines" or r["status"] == "running")}, "payload": json.loads(r["payload"])}
                for r in rows if r["id"] is not None]
        meta = next((r for r in rows if r["id"] is None), {})
        return {"queued": [j for j in jobs if j["status"] == "queued"], "running_github": [j for j in jobs if j["status"] == "running"],
                "last_nightly": meta.get("last_nightly"), "last_weekly": meta.get("last_weekly"),
                "untagged": meta.get("untagged") or 0, "open_kinds": set((meta.get("open_kinds") or "").split(",")) - {""}}

    def untagged(self, limit=wire.TAG_BATCH) -> list[dict]:
        return wire.untagged(self.query, limit)


def gh_starter(workflows: dict, run=subprocess.run, repo=wire.ENGINE):
    """`start_github(job)`: `gh workflow run` the file mapped to the job's kind in the public engine repo. A mapping that is
    a plain file name passes the job id and the payload as they are; one from `wire.WORKFLOWS` renames the payload to the
    workflow's declared inputs."""
    def start(row):
        wf = workflows.get(row["kind"])
        if not wf:
            raise NotWired(row["kind"])
        if isinstance(wf, dict):
            file, inputs = wf["file"], wire.workflow_inputs(row["kind"], row["payload"], row["id"])
        else:
            file, inputs = wf, {"job_id": row["id"], **{k: str(v) for k, v in row["payload"].items()}}
        args = ["gh", "workflow", "run", file, "--repo", repo]
        for key, value in inputs.items():
            args += ["-f", f"{key}={value}"]
        done = run(args, capture_output=True, text=True, timeout=60)
        if done.returncode != 0:
            raise RuntimeError(done.stderr[:200])
    return start


def gh_checker(workflows: dict, run=subprocess.run, repo=wire.ENGINE, grace=timedelta(minutes=30)):
    """`check_github(job)`: None while the run is going, "success" or "failure" once it ended. The workflows name each run
    after the job id (`run-name`), so the run is found by title. A run that never shows up within `grace` counts as failed."""
    import json

    def check(row):
        wf = workflows.get(row["kind"])
        file = wf["file"] if isinstance(wf, dict) else wf
        if not file:
            return None
        done = run(["gh", "run", "list", "--repo", repo, "--workflow", file, "--limit", "30", "--json", "displayTitle,status,conclusion"],
                   capture_output=True, text=True, timeout=60)
        if done.returncode != 0:
            return None
        for r in json.loads(done.stdout or "[]"):
            if r["displayTitle"] == row["id"]:
                return None if r["status"] != "completed" else "success" if r["conclusion"] == "success" else "failure"
        started = datetime.fromisoformat(row["started_at"]) if row.get("started_at") else None
        return "failure" if started and datetime.now(IST) - started > grace else None
    return check


def _handlers(cfg, deps) -> dict:
    """Every kind the VM runs itself (see `wire.handlers`), and `sync` through the Worker's Kite read when the key is set."""
    from stockpilot import store
    from stockpilot.jobs import sync
    from stockpilot.sources import kite
    handlers = wire.handlers(deps)
    key, url = cfg.secret("SP_VM_KEY"), cfg.get("worker.url")
    if key and url:
        path = cfg.root / cfg.get("store.path", "data/stockpilot.duckdb")
        handlers["sync"] = sync.handler(lambda: store.open(path, job="sync", wait_s=120), kite.Worker(url, key),
                                        close=lambda db: db.close())
    return handlers


def run(cfg) -> int:
    """One firing wired for production. Imports stay inside so an unconfigured or idle firing is as small as it can be."""
    import json
    import os
    import sys
    from pathlib import Path
    names = ("CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")
    account, token = (cfg.secret(n) for n in names)
    database = cfg.get("d1.database_id")
    if not (account and token and database):
        print("Minute check is not set up: needs CLOUDFLARE_ACCOUNT_ID, CLOUDFLARE_API_TOKEN and d1.database_id.", file=sys.stderr)
        return 75
    from stockpilot.jobrun import SqliteSink
    state_file = Path.home() / ".cache" / "stockpilot-minute" / "state.json"
    try:
        state = json.loads(state_file.read_text())
    except (OSError, ValueError):
        state = {}
    env = {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": cfg.secret("CLAUDE_CODE_OAUTH_TOKEN") or ""}

    def alarm(text):
        def gh(*args):
            return subprocess.run(["gh", *args], cwd=cfg.root, capture_output=True, text=True, check=True).stdout
        key = "stale-pipeline"
        if key not in gh("issue", "list", "--label", "self-heal", "--state", "open", "--search", key):
            gh("issue", "create", "--label", "self-heal", "--title", f"[self-heal] {key}", "--body", text)
        print("ALARM:", text, file=sys.stderr)

    query = cloudflare_query(account, database, token)
    sink, now = SqliteSink(D1Db(query)), (lambda: datetime.now(IST))
    make = lambda name: CliBackend(name, env={**env, **(cfg.get(f"minute.env.{name}", {}) or {})})  # noqa: E731
    enqueue = lambda kind, payload, by: JobRunner(sink, clock=now).enqueue(kind, payload, by)  # noqa: E731
    deps = wire.production_deps(cfg, query, now, state, enqueue, make)
    workflows = {**wire.WORKFLOWS, **(cfg.get("minute.workflows", {}) or {})}
    repo = cfg.get("public_data.repo", wire.ENGINE)
    before = json.dumps(state, sort_keys=True)
    out = tick(D1Source(query), sink, make_backend=make, handlers=_handlers(cfg, deps),
               start_github=gh_starter(workflows, repo=repo), alarm=alarm, state=state, now=now, enqueue=enqueue,
               check_github=gh_checker(workflows, repo=repo))
    if json.dumps(state, sort_keys=True) != before:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state))
    if out["ran"] or out["started"] or out["alarm"] or len(out) > 3:
        print(out)
    return 0


if __name__ == "__main__":
    import sys
    from stockpilot import config
    root = sys.argv[sys.argv.index("--root") + 1] if "--root" in sys.argv else "."
    sys.exit(run(config.load(root)))
