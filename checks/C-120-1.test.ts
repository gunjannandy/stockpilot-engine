// C-120-1: data files carry immutable cache headers; the bundle has no data.
import { readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { expect, it } from "vitest";
import { repoRoot } from "../api/migrate/discover";
import checks from "../api/src/data/checks";
import { publishApp } from "../api/src/publish/testkit";

const sha = "cd".repeat(32);
const name = `big.${sha.slice(0, 12)}.json`;

function walk(dir: string, out: string[] = []): string[] {
  for (const e of readdirSync(dir, { withFileTypes: true })) {
    if (e.name === "node_modules" || e.name === "dist") continue;
    const p = join(dir, e.name);
    if (e.isDirectory()) walk(p, out);
    else out.push(p);
  }
  return out;
}

it("C-120-1 /data files pass through with year-long immutable caching", async () => {
  const asked: string[] = [];
  const fake = (async (url: string) => {
    asked.push(url);
    return url.endsWith(name) ? new Response('{"rows":[]}') : new Response("no", { status: 404 });
  }) as unknown as typeof fetch;
  const t = await publishApp({ fetch: fake });
  const ok = await t.app.request(`/data/${name}`);
  expect(ok.status).toBe(200);
  expect(ok.headers.get("cache-control")).toBe("public, max-age=31536000, immutable");
  expect(await ok.text()).toBe('{"rows":[]}');

  // Only content-hashed names go to the release; anything else is refused before any fetch.
  const before = asked.length;
  for (const bad of ["big.json", "../x.0123456789ab.json", "Big.0123456789ab.json"])
    expect((await t.app.request(`/data/${encodeURIComponent(bad)}`)).status).toBe(404);
  expect(asked.length).toBe(before);
  const miss = await t.app.request("/data/big.0123456789ab.json");
  expect(miss.status).toBe(404);
  expect(miss.headers.get("cache-control")).toBe("no-store");
});

it("C-120-1 the production check passes on served files and fails on a missing one", async () => {
  const good = (async () => new Response("{}")) as unknown as typeof fetch;
  const t = await publishApp({ fetch: good });
  const check = checks[0];
  await t.read("roomy"); // first request applies the migrations
  const ctxFor = (app: typeof t.app) =>
    ({ d1: t.db, call: (p: string, i?: RequestInit) => app.request(p, i) }) as never;
  expect((await check?.run(ctxFor(t.app), { startedAt: "" }))?.ok).toBe(true); // no files yet
  await t.finish("big", "a", { ...t.prov("big", "a"), file: { name, sha256: sha, rows: 3 } });
  const res = await check?.run(ctxFor(t.app), { startedAt: "" });
  expect(res).toMatchObject({ ok: true });

  const gone = await publishApp({
    fetch: (async () => new Response("x", { status: 404 })) as unknown as typeof fetch,
  });
  await gone.finish("big", "a", { ...gone.prov("big", "a"), file: { name, sha256: sha, rows: 3 } });
  const bad = await check?.run(
    { d1: gone.db, call: (p: string, i?: RequestInit) => gone.app.request(p, i) } as never,
    { startedAt: "" },
  );
  expect(bad?.ok).toBe(false);
});

it("C-120-1 the bundle holds no data files", () => {
  const dirs = ["web/src", "web/public", "web/index.html"].map((d) => join(repoRoot, d));
  const data = dirs.flatMap((d) => {
    try {
      return statSync(d).isDirectory() ? walk(d) : [d];
    } catch {
      return [];
    }
  });
  const bulky = data.filter(
    (f) =>
      /\.(json|csv|parquet|ndjson)$/.test(f) && !f.includes("/words/") && statSync(f).size > 20_000,
  );
  expect(bulky).toEqual([]);
});
