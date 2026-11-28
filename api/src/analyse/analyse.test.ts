import type { AnalyseCall } from "@stockpilot/contract";
import { describe, expect, it } from "vitest";
import { SqliteD1 } from "../../../adapters/src/core";
import { fakeGithub } from "../../../adapters/src/github";
import { loadRegistry } from "../../migrate/discover";
import { createApp } from "../app";
import { KEY, makeApp } from "../testkit";
import { analyseRoutes } from "./routes";

const call = (over: Partial<AnalyseCall> = {}): AnalyseCall => ({
  symbol: "ABC",
  day: "2026-11-28",
  call: "buy",
  chance_pct: 62,
  source: "model",
  summary_en: "Cheap.",
  summary_bn: "সস্তা।",
  reasons: [{ text_en: "P/E 12.", text_bn: "P/E ১২।", evidence: ["fact:pe"] }],
  risks: [],
  model: "haiku",
  note: null,
  ...over,
});

describe("analyse routes", () => {
  it("stores one call per stock and day and reads the newest back", async () => {
    const t = await makeApp();
    expect((await t.signed("POST", "/api/analyse/call", call())).status).toBe(200);
    expect((await t.signed("POST", "/api/analyse/call", call({ chance_pct: 65 }))).status).toBe(
      200,
    );
    const r = (await (await t.app.request("/api/analyse/abc")).json()) as {
      call: { chance_pct: number; reasons: unknown[] };
    };
    expect(r.call.chance_pct).toBe(65);
    expect(r.call.reasons).toHaveLength(1);
  });

  it("refuses a model call without Bengali (C-039-1 at the door)", async () => {
    const t = await makeApp();
    const res = await t.signed("POST", "/api/analyse/call", call({ summary_bn: "Cheap." }));
    expect(res.status).toBe(422);
  });

  it("serves public inputs to a signed Job only", async () => {
    const t = await makeApp();
    expect((await t.app.request("/api/analyse/inputs/ABC")).status).toBe(401);
    const res = await t.signed("GET", "/api/analyse/inputs/ABC");
    expect(res.status).toBe(200);
    const body = (await res.json()) as { facts: unknown; history: unknown[]; news: unknown[] };
    expect(body.facts).toBeNull();
    expect(body.history).toEqual([]);
  });

  it("has no holding, tax or account column", async () => {
    const t = await makeApp();
    const cols = (await t.db
      .prepare("select name from pragma_table_info('analyse_calls')")
      .all()) as { results: { name: string }[] };
    expect(cols.results.map((c) => c.name).join(" ")).not.toMatch(/hold|tax|account|lot|qty/);
  });

  it("the button dispatches the Job at once, and a second press shows the same Job", async () => {
    const github = fakeGithub();
    const registry = await loadRegistry();
    registry.areas = registry.areas.map((a) =>
      a.name === "analyse" ? { ...a, routes: (ctx) => analyseRoutes(ctx, { github }) } : a,
    );
    const app = createApp({
      d1: new SqliteD1(),
      env: { INGEST_HMAC_KEY: KEY, HEALTH_SECRET: "h".repeat(24), SP_ENV: "dev" } as never,
      registry,
    });
    const first = await app.request("/api/analyse/abc/run", { method: "POST" });
    expect(first.status).toBe(202);
    expect(github.dispatched).toHaveLength(1);
    expect(github.dispatched[0]?.workflow).toBe("analyse.yml");
    expect(github.dispatched[0]?.inputs.subject).toBe("ABC");
    const second = await app.request("/api/analyse/abc/run", { method: "POST" });
    expect(second.status).toBe(200);
    expect(github.dispatched).toHaveLength(1);
    expect((await app.request("/api/analyse/ABC%21/run", { method: "POST" })).status).toBe(400);
  });
});
