// C-045-1: an unknown symbol starts one load Job and reports progress.
import { expect, it } from "vitest";
import { SqliteD1 } from "../adapters/src/core";
import { fakeGithub } from "../adapters/src/github";
import { loadRegistry } from "../api/migrate/discover";
import { createApp } from "../api/src/app";
import { jobRoutes } from "../api/src/jobs/routes";
import { stocksRoutes } from "../api/src/stocks/routes";
import { HEALTH, KEY } from "../api/src/testkit";

async function build() {
  const github = fakeGithub({});
  const registry = await loadRegistry();
  registry.areas = registry.areas.map((a) =>
    a.name === "stocks"
      ? { ...a, routes: (ctx) => stocksRoutes(ctx, { github }) }
      : a.name === "jobs"
        ? { ...a, routes: (ctx) => jobRoutes(ctx) }
        : a,
  );
  const env = { INGEST_HMAC_KEY: KEY, HEALTH_SECRET: HEALTH, SP_ENV: "dev" } as never;
  const app = createApp({ d1: new SqliteD1(), env, registry, version: "v1" });
  return { app, github };
}
const post = (app: ReturnType<typeof createApp>, path: string) =>
  app.request(path, { method: "POST" });

it("C-045-1 an unknown symbol starts one load Job, and asking again shows the same Job", async () => {
  const { app, github } = await build();
  const known = await (await app.request("/api/stocks/NEWCO")).json();
  expect(known.known).toBe(false);
  expect(known.load).toBeNull();

  const first = await post(app, "/api/stocks/NEWCO/load");
  expect(first.status).toBe(202);
  const job = await first.json();
  expect(job.state).toBe("queued");
  expect(job.key).toMatch(/^history\|NEWCO\|/);

  const again = await post(app, "/api/stocks/NEWCO/load");
  expect((await again.json()).key).toBe(job.key);
  const sent = (github as unknown as { dispatched?: unknown[] }).dispatched ?? [];
  expect(sent.length).toBeLessThanOrEqual(1);

  const page = await (await app.request("/api/stocks/NEWCO")).json();
  expect(page.load).toMatchObject({ state: "queued", key: job.key });
});

it("C-045-1 a bad symbol is refused", async () => {
  const { app } = await build();
  expect((await post(app, "/api/stocks/bad%20symbol!/load")).status).toBe(400);
});
