// Steps `promote.yml` runs (story 135): read the pause flag, post What's new lines, wait for the
// deploy, run the check runner. Pure functions are exported for tests; the CLI is at the bottom.
import { execFileSync } from "node:child_process";
import { sign } from "../src/app";

export type Line = { pr: number; en: string; bn: string };

/** A UI PR body carries `What's new (en): ...` and `What's new (bn): ...` lines. */
export function extractWhatsNew(pr: number, body: string): Line | null {
  const pick = (label: string) =>
    new RegExp(
      `^\\s*[-*]?\\s*what['’]s new\\s*\\(\\s*(?:${label})\\s*\\)\\s*:\\s*(.+?)\\s*$`,
      "im",
    ).exec(body)?.[1];
  const en = pick("en|english");
  const bn = pick("bn|bengali|bangla");
  return en && bn ? { pr, en, bn } : null;
}

/** PR numbers named in commit subjects between two shas, as squash and queue merges write them. */
export function prNumbers(subjects: string[]): number[] {
  return [
    ...new Set(
      subjects.flatMap((s) => [...s.matchAll(/\(#(\d+)\)\s*$/gm)].map((m) => Number(m[1]))),
    ),
  ];
}

const env = (k: string) => {
  const v = process.env[k];
  if (!v) throw new Error(`${k} is not set`);
  return v;
};
const base = () => env("API_URL").replace(/\/$/, "");
async function signedPost(path: string, body: unknown) {
  const raw = body === undefined ? "" : JSON.stringify(body);
  return fetch(base() + path, {
    method: "POST",
    body: body === undefined ? undefined : raw,
    headers: {
      "content-type": "application/json",
      "x-signature": await sign(env("INGEST_HMAC_KEY"), raw),
    },
  });
}
const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

async function main(cmd: string, args: string[]) {
  if (cmd === "paused") {
    const s = (await (await fetch(`${base()}/api/status`)).json()) as { paused: boolean };
    console.log(s.paused ? "true" : "false");
  } else if (cmd === "whatsnew") {
    const [from, to] = args;
    const log = execFileSync("git", [
      "log",
      "--format=%s",
      from ? `${from}..${to}` : `-1`,
      ...(from ? [] : [to as string]),
    ])
      .toString()
      .split("\n");
    const lines: Line[] = [];
    for (const n of prNumbers(log)) {
      const body = execFileSync("gh", [
        "api",
        `repos/${env("REPO")}/pulls/${n}`,
        "--jq",
        '.body // ""',
      ]).toString();
      const l = extractWhatsNew(n, body);
      if (l) lines.push(l);
    }
    if (lines.length === 0) return console.log("no What's new lines to post");
    const res = await signedPost("/api/whatsnew", { lines });
    if (!res.ok) throw new Error(`whatsnew answered ${res.status}`);
    console.log(`posted ${lines.length} What's new line(s)`);
  } else if (cmd === "wait") {
    const [sha, minutes = "15"] = args;
    for (let i = 0; i < Number(minutes) * 3; i++) {
      const s = await fetch(`${base()}/api/status`)
        .then((r) => r.json() as Promise<{ version?: string }>)
        .catch(() => ({}) as { version?: string });
      if (s.version === sha) return console.log(`production runs ${sha}`);
      await sleep(20000);
    }
    throw new Error(`production did not reach ${sha} in ${minutes} minutes`);
  } else if (cmd === "checks") {
    const res = await signedPost("/api/checks/run", undefined);
    if (!res.ok) throw new Error(`check runner answered ${res.status}`);
    const { results } = (await res.json()) as {
      results: { id: string; ok: boolean; detail: string }[];
    };
    for (const r of results) console.log(`${r.ok ? "green" : "RED  "} ${r.id} ${r.detail}`);
    if (results.some((r) => !r.ok)) process.exit(1);
  } else {
    throw new Error("usage: promote.ts paused | whatsnew <from> <to> | wait <sha> | checks");
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  main(process.argv[2] ?? "", process.argv.slice(3)).catch((e) => {
    console.error(e instanceof Error ? e.message : e);
    process.exit(1);
  });
}
