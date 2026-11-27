"""REST calls for the trace sync PR, through `gh api` (GraphQL is blocked in cloud sessions)."""
import base64
import json
import subprocess

REPO = "stockpilot-hq/stockpilot-engine"


def _api(method, path, data=None):
    args = ["gh", "api", "-X", method, f"repos/{REPO}/{path}"]
    if data is not None:
        args += ["--input", "-"]
    res = subprocess.run(args, input=json.dumps(data) if data is not None else None, capture_output=True, text=True)
    if res.returncode:
        raise RuntimeError(res.stderr.strip())
    return json.loads(res.stdout) if res.stdout.strip() else {}


def runner(verb, **kw):
    if verb == "branch":
        sha = _api("GET", f"git/ref/heads/{kw['base']}")["object"]["sha"]
        return _api("POST", "git/refs", {"ref": f"refs/heads/{kw['name']}", "sha": sha})
    if verb == "put_file":
        body = {"message": kw["message"], "branch": kw["branch"],
                "content": base64.b64encode(kw["content"].encode()).decode()}
        try:
            body["sha"] = _api("GET", f"contents/{kw['path']}?ref={kw['branch']}")["sha"]
        except RuntimeError:
            pass
        return _api("PUT", f"contents/{kw['path']}", body)
    if verb == "open_pr":
        return _api("POST", "pulls", {k: kw[k] for k in ("head", "base", "title", "body")} | {"draft": False})
    raise ValueError(verb)
