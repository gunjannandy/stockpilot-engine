"""Cloudflare D1 over its REST query endpoint: the real Source (production) and Target (preview) for the Jobs."""
import json
import urllib.request
from collections.abc import Callable, Iterator

PAGE = 500
BATCH = 50   # rows per insert statement group; D1 caps bound parameters per query

Post = Callable[[str, dict[str, str], bytes], dict]


def _post(url: str, headers: dict[str, str], body: bytes) -> dict:
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read())


def _q(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


class D1:
    def __init__(self, account: str, database: str, token: str, post: Post = _post):
        self.url = f"https://api.cloudflare.com/client/v4/accounts/{account}/d1/database/{database}/query"
        self.headers = {"authorization": f"Bearer {token}", "content-type": "application/json"}
        self.post = post

    def query(self, sql: str, params: list | None = None) -> list[dict]:
        out = self.post(self.url, self.headers, json.dumps({"sql": sql, "params": params or []}).encode())
        if not out.get("success"):
            raise RuntimeError(f"D1 refused the query: {out.get('errors')}")
        return out["result"][0].get("results", [])

    def tables(self) -> list[str]:
        return [r["name"] for r in self.query("select name from sqlite_master where type = 'table' order by name")]

    def pages(self, table: str) -> Iterator[list[dict]]:
        offset = 0
        while True:
            rows = self.query(f"select * from {_q(table)} order by rowid limit {PAGE} offset {offset}")
            if not rows:
                return
            yield rows
            offset += PAGE

    def count(self, table: str) -> int | None:
        try:
            return int(self.query(f"select count(*) as n from {_q(table)}")[0]["n"])
        except RuntimeError:
            return None

    def replace(self, table: str, rows: list[dict]) -> None:
        self.query(f"delete from {_q(table)}")
        for i in range(0, len(rows), BATCH):
            for row in rows[i:i + BATCH]:
                cols = list(row)
                self.query(f"insert into {_q(table)} ({', '.join(map(_q, cols))}) values ({', '.join('?' * len(cols))})",
                           [row[c] for c in cols])
