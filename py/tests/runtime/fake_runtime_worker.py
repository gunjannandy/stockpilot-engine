"""A fake Worker for the runtime tests: the begin/end, publish and model routes, in memory."""
import json

KEY = "k" * 40


class FakeRuntimeWorker:
    def __init__(self, cap: int = 2):
        self.runs: dict[str, dict] = {}        # key -> row
        self.rows: dict[str, dict] = {}        # dataset -> {id: row} of the last published run
        self.staged: dict[tuple, list] = {}
        self.cache: dict[str, str] = {}
        self.cap, self.used = cap, 0
        self.calls: list[tuple[str, str]] = []
        self.refuse_begin: tuple[int, str] | None = None
        self.fail_rows: str | None = None

    def transport(self, method, url, headers, body):
        path = "/" + url.split("/", 3)[3]
        self.calls.append((method, path.split("?")[0]))
        data = json.loads(body) if body else {}
        route = path.split("?")[0]
        if route == "/api/job/begin":
            if self.refuse_begin:
                return self.refuse_begin[0], {"error": self.refuse_begin[1]}
            key = f"{data['kind']}|{data['subject']}|{data.get('day', '*')}"
            if key in self.runs and self.runs[key]["status"] in ("running", "done") and not data.get("rerun"):
                return 409, {"error": f"duplicate: {key}"}
            self.runs[key] = {"status": "running", "run_id": data["run_id"], "range": (data.get("from"), data.get("to"))}
            return 200, {"run_id": data["run_id"], "key": key, "started_at": "2026-11-27T10:00:00+05:30",
                         "expected_seconds": 12, "range": {"from": data.get("from"), "to": data.get("to")}}
        if route == "/api/job/end":
            for row in self.runs.values():
                if row["run_id"] == data["run_id"]:
                    row.update(status=data["status"], error=data.get("error"), result=data.get("result"))
                    return 200, {"ok": True, "retry_at": None}
            return 404, {"error": "no running Job"}
        if route == "/api/publish/rows":
            if self.fail_rows:
                return 400, {"error": self.fail_rows}
            self.staged.setdefault((data["dataset"], data["run_id"]), []).extend(data["rows"])
            return 200, {"accepted": len(data["rows"]), "held_back": 0}
        if route == "/api/publish/finish":
            staged = self.staged.pop((data["dataset"], data["run_id"]), [])
            self.rows[data["dataset"]] = {r["id"]: r for r in staged}
            return 200, {"published": True}
        if route == "/api/model/claim":
            if (k := (data["kind"], data["model"], data["brief_hash"])) and str(k) in self.cache:
                return 200, {"cached": True, "answer": self.cache[str(k)]}
            if self.used >= self.cap:
                return 429, {"error": "daily cap reached", "message": "Next update tomorrow"}
            self.used += 1
            return 200, {"cached": False, "left": self.cap - self.used}
        if route == "/api/model/answer":
            self.cache[str((data["kind"], data["model"], data["brief_hash"]))] = data["answer"]
            return 200, {"ok": True}
        if route == "/api/heartbeat":
            return 400, {"error": "unknown part"}
        return 404, {"error": "no route"}
