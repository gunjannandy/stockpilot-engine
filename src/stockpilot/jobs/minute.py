"""The one-minute check (ticket V1): runs as a systemd oneshot timer, never as a daemon.

One firing: ask the job source for queued work (one cheap read; nothing queued means exit at once), hand each model job to
`JobRunner` with a fallback `Chain`, start GitHub jobs through the injected `start_github`, and raise the stale-pipeline
alarm through the injected `alarm`. Model order: forecasts Sonnet then Gemini, then a plain "usage is used up" message;
tagging and reading feedback Gemini account A, then B, then Haiku. All I/O is injected, so tests use fakes and spend nothing."""
import subprocess
import tempfile
from datetime import datetime, timedelta

from stockpilot.jobrun import CONTRACT, IST, JobFailed, JobRunner

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


def chain_for(kind: str, make) -> Chain:
    """`make(name)` builds one backend by name; the chain for a kind is fixed here."""
    return Chain([make(name) for name in CHAINS[kind]])


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


ANALYSE_PROMPT = ("Analyse the stock {symbol} on {exchange} for a long-term Indian investor. Reply in plain English, short: "
                  "what to do today (buy, hold, sell or nothing), the chance it is right, the price range you expect, "
                  "and the two reasons that matter most.")
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


def tick(source, sink, *, make_backend, handlers, start_github, alarm, state, now, budget_s=240) -> dict:
    """One firing. `source.pending()` is the only read: `{"queued": [job rows], "last_nightly": time or None}`.
    A job whose kind has no handler (or runs elsewhere) stays queued for whoever owns it."""
    started = now()
    seen = source.pending()
    ran = began = 0
    for row in seen["queued"]:
        runs_on = CONTRACT["job_kinds"].get(row["kind"], {}).get("runs_on")
        if runs_on == "github_public":
            began += _start_github(sink, row, start_github, now)
        elif runs_on == "vm_model" and row["kind"] in handlers and now() - started < timedelta(seconds=budget_s):
            _adopt(sink, row)
            runner = JobRunner(sink, model=chain_for(row["kind"], make_backend), clock=now)
            runner.register(row["kind"], handlers[row["kind"]])
            runner.run(row["id"])
            ran += 1
    raised = _stale(seen.get("last_nightly"), started, state)
    if raised:
        alarm(STALE_TEXT)
        state["last_alarm"] = started.isoformat()
    return {"ran": ran, "started": began, "alarm": raised}


def _adopt(sink, row):
    if row["id"] not in sink.jobs:
        sink.create_job(row)


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
PENDING_SQL = (f"select {_COLS}, null as last_nightly from jobs where status = 'queued' "
               f"union all select null, null, null, null, null, null, null, null, null, null, null, max(finished_at) "
               f"from jobs where kind = 'nightly' and status = 'done' order by created_at")


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
    """`pending()` is one query: the queued jobs, oldest first, plus when the last nightly job finished."""

    def __init__(self, query):
        self.query = query

    def pending(self) -> dict:
        import json
        rows = self.query(PENDING_SQL)
        queued = [{**{k: v for k, v in r.items() if k != "last_nightly"}, "payload": json.loads(r["payload"])}
                  for r in rows if r["id"] is not None]
        last = next((r["last_nightly"] for r in rows if r["id"] is None), None)
        return {"queued": queued, "last_nightly": last}


def gh_starter(workflows: dict, run=subprocess.run, repo="gunjannandy/stockpilot"):
    """`start_github(job)`: `gh workflow run` the file mapped to the job's kind, passing the job id and payload as inputs."""
    def start(row):
        wf = workflows.get(row["kind"])
        if not wf:
            raise NotWired(row["kind"])
        args = ["gh", "workflow", "run", wf, "--repo", repo, "-f", f"job_id={row['id']}"]
        for key, value in row["payload"].items():
            args += ["-f", f"{key}={value}"]
        done = run(args, capture_output=True, text=True, timeout=60)
        if done.returncode != 0:
            raise RuntimeError(done.stderr[:200])
    return start


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
    out = tick(D1Source(query), SqliteSink(D1Db(query)),
               make_backend=lambda name: CliBackend(name, env={**env, **(cfg.get(f"minute.env.{name}", {}) or {})}),
               handlers={"analyse": ask_handler(ANALYSE_PROMPT)},
               start_github=gh_starter(cfg.get("minute.workflows", {}) or {}), alarm=alarm, state=state,
               now=lambda: datetime.now(IST))
    if out["alarm"]:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        state_file.write_text(json.dumps(state))
    if out["ran"] or out["started"] or out["alarm"]:
        print(out)
    return 0


if __name__ == "__main__":
    import sys
    from stockpilot import config
    root = sys.argv[sys.argv.index("--root") + 1] if "--root" in sys.argv else "."
    sys.exit(run(config.load(root)))
