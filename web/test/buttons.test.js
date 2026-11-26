// QUEUE (#114): the page's buttons post D1 jobs through /api/v2/jobs; nothing goes to /api/queue any more.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import "../public/buttons.js";
const B = globalThis.SPButtons;
const contract = JSON.parse(readFileSync(new URL("../../schemas/live-contract.json", import.meta.url), "utf8"));
const old = JSON.parse(readFileSync(new URL("../../schemas/queue-kinds.json", import.meta.url), "utf8")).kinds;
const reply = (status, body = {}) => ({ ok: status < 300, status, json: async () => body });

describe("plan: which route each of the old kinds now takes", () => {
  it("every old kind except feedback_decide has a route, and job kinds are in the contract with the same keys", () => {
    for (const kind of Object.keys(old).filter(k => k !== "feedback_decide")) {
      const p = B.plan(kind, Object.fromEntries(old[kind].map(k => [k, k === "symbol" ? "SBIN" : "x"])));
      expect(p, kind).toBeTruthy();
      if (p.url === "/api/v2/jobs") {
        const spec = contract.job_kinds[p.body.kind];
        expect(spec, kind).toBeTruthy();
        expect(Object.keys(p.body.payload).sort(), kind).toEqual([...spec.payload].sort());
      }
    }
  });
  it("feedback goes to the feedback route and ask_analyst becomes an analyse job", () => {
    expect(B.plan("feedback", { text: "chart bhalo", kind: null })).toEqual({ url: "/api/v2/feedback", body: { text: "chart bhalo" } });
    expect(B.plan("ask_analyst", { symbol: "SBIN" })).toEqual({ url: "/api/v2/jobs", body: { kind: "analyse", payload: { symbol: "SBIN", exchange: "NSE" } } });
  });
  it("nothing posts to the KV queue", () => {
    expect(readFileSync(new URL("../public/buttons.js", import.meta.url), "utf8")).not.toContain("/api/queue");
  });
});

describe("send", () => {
  it("posts the plan and returns the job id; 401 and 429 are told apart", async () => {
    const seen = [];
    const f = (u, i) => { seen.push([u, JSON.parse(i.body)]); return Promise.resolve(reply(200, { id: "job_1" })); };
    expect(await B.send(f, "snooze", { symbol: "TCS", scope: "stock" })).toEqual({ ok: true, id: "job_1" });
    expect(seen[0]).toEqual(["/api/v2/jobs", { kind: "snooze", payload: { symbol: "TCS", scope: "stock" } }]);
    expect((await B.send(() => Promise.resolve(reply(401)), "rerun", { job: "daily" })).status).toBe(401);
    expect((await B.send(() => Promise.resolve(reply(429)), "rerun", { job: "daily" })).status).toBe(429);
    expect((await B.send(() => Promise.reject(new Error("x")), "rerun", { job: "daily" })).ok).toBe(false);
  });
});

describe("undo is the opposite job", () => {
  it("star, unstar and the long-term mark have one; the rest do not", () => {
    expect(B.inverse("watchlist_add", { symbol: "A", exchange: "NSE" })).toEqual({ kind: "watchlist_remove", payload: { symbol: "A", exchange: "NSE" } });
    expect(B.inverse("long_term_mark", { symbol: "A", on: true })).toEqual({ kind: "long_term_mark", payload: { symbol: "A", on: false } });
    expect(B.inverse("budget_set", { month: "2026-12", amount: 1 })).toBeNull();
  });
});

describe("items: the owner's jobs list in the shape the Health table reads", () => {
  it("maps status and error to the old note", () => {
    const got = B.items([{ id: "job_2", kind: "snooze", payload: { symbol: "A" }, status: "failed", error: "Nope.", created_at: "2026-11-26T09:00:00+05:30" },
                         { id: "job_1", kind: "analyse", payload: {}, status: "running", result: null, created_at: "2026-11-26T08:00:00+05:30" }]);
    expect(got[0]).toMatchObject({ id: "job_1", status: "taken", at: "2026-11-26T08:00:00+05:30" });
    expect(got[1]).toMatchObject({ id: "job_2", status: "failed", note: "Nope." });
  });
});
