import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { FakeKV, ctx, startFakeKite } from "./helpers.js";
import { onRequestGet as login } from "../functions/kite/login.js";
import { onRequestGet as callback } from "../functions/kite/callback.js";
import { onRequestGet as vmKite } from "../functions/api/vm/kite.js";
import { secondsUntilSix } from "../lib/kite.js";

let kite;
beforeAll(async () => { kite = await startFakeKite(); });
afterAll(() => kite.close());
const mkEnv = () => ({ SP: new FakeKV(), KITE_API_KEY: kite.apiKey, KITE_API_SECRET: kite.apiSecret, KITE_API_BASE: kite.base, KITE_LOGIN_BASE: "https://login.example" });
const O = "https://sp.test";

describe("kite flow against a fake Kite", () => {
  it("full flow: no token is 409, login redirects, callback stores the token, the VM gets all six reads", async () => {
    const env = mkEnv();
    let r = await vmKite(ctx(`${O}/api/vm/kite`, env));
    expect(r.status).toBe(409);
    expect(await r.json()).toEqual({ login_needed: true });

    r = await login(ctx(`${O}/kite/login`, env));
    expect(r.status).toBe(302);
    expect(r.headers.get("location")).toBe("https://login.example/connect/login?v=3&api_key=key123");

    r = await callback(ctx(`${O}/kite/callback?request_token=reqtok&status=success`, env));
    expect(r.status).toBe(302);
    expect(r.headers.get("location")).toBe(`${O}/?synced=1`);
    expect(env.SP.m.get("kite:token").ttl).toBeGreaterThan(0);
    expect(env.SP.m.get("kite:token").ttl).toBeLessThanOrEqual(24 * 3600);

    r = await vmKite(ctx(`${O}/api/vm/kite`, env));
    expect(r.status).toBe(200);
    const body = await r.json();
    expect(Object.keys(body).sort()).toEqual(["fetched_at", "gtts", "holdings", "margins", "mf_holdings", "positions", "trades"]);
    expect(body.holdings[0].tradingsymbol).toBe("SBIN");
    expect(JSON.stringify(body)).not.toContain("acc789");
  });

  it("a completed login queues a Kite pull, so holdings arrive within one queue tick", async () => {
    const env = mkEnv();
    await callback(ctx(`${O}/kite/callback?request_token=reqtok&status=success`, env));
    const queued = [...env.SP.m.entries()].filter(([k]) => k.startsWith("q:")).map(([, v]) => JSON.parse(v.v));
    expect(queued.map((q) => [q.kind, q.payload])).toEqual([["rerun", { job: "kite" }]]);
  });

  it("a bad request token stores nothing", async () => {
    const env = mkEnv();
    const r = await callback(ctx(`${O}/kite/callback?request_token=wrong`, env));
    expect(r.status).toBe(502);
    expect(env.SP.m.size).toBe(0);
  });

  it("a missing request token or a cancelled login is a 400", async () => {
    const env = mkEnv();
    expect((await callback(ctx(`${O}/kite/callback`, env))).status).toBe(400);
    expect((await callback(ctx(`${O}/kite/callback?request_token=x&status=error`, env))).status).toBe(400);
  });

  it("an expired token (Kite 403) is dropped and the VM is told to log in again", async () => {
    const env = mkEnv();
    await env.SP.put("kite:token", "stale");
    const r = await vmKite(ctx(`${O}/api/vm/kite`, env));
    expect(r.status).toBe(409);
    expect(env.SP.m.has("kite:token")).toBe(false);
  });

  it("only GET reads and the session exchange hit Kite", async () => {
    const env = mkEnv();
    kite.calls.length = 0;
    await callback(ctx(`${O}/kite/callback?request_token=reqtok`, env));
    await vmKite(ctx(`${O}/api/vm/kite`, env));
    const allowed = new Set(["POST /session/token", "GET /portfolio/holdings", "GET /mf/holdings", "GET /trades",
      "GET /portfolio/positions", "GET /user/margins", "GET /gtt/triggers"]);
    expect(kite.calls.length).toBe(7);
    for (const c of kite.calls) expect(allowed.has(`${c.method} ${c.path}`)).toBe(true);
  });

  it("the token lives until 06:00 IST", () => {
    expect(secondsUntilSix(new Date("2026-11-23T00:00:00Z"))).toBe(30 * 60);
    expect(secondsUntilSix(new Date("2026-11-23T00:30:00Z"))).toBe(24 * 3600);
    expect(secondsUntilSix(new Date("2026-11-23T12:30:00Z"))).toBe(12 * 3600);
  });
});

describe("V2: the callback creates a Sync job the page can follow", () => {
  it("a completed login inserts a queued sync job in D1 and sends the browser to it", async () => {
    const { localD1 } = await import("./d1.js");
    const env = { ...mkEnv(), DB: localD1({ seed: false }) };
    const r = await callback(ctx(`${O}/kite/callback?request_token=reqtok&status=success`, env));
    const job = env.DB.db.prepare("select * from jobs where kind = 'sync'").all();
    expect(job.length).toBe(1);
    expect(job[0].status).toBe("queued");
    expect(JSON.parse(job[0].payload)).toEqual({});
    expect(r.headers.get("location")).toBe(`${O}/?synced=1&job=${job[0].id}`);
  });
  it("a refused login creates no job", async () => {
    const { localD1 } = await import("./d1.js");
    const env = { ...mkEnv(), DB: localD1({ seed: false }) };
    await callback(ctx(`${O}/kite/callback?request_token=wrong`, env));
    expect(env.DB.db.prepare("select count(*) as n from jobs").get().n).toBe(0);
  });
});
