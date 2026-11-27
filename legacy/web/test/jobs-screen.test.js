// T28: the Jobs screen. Every job kind renders, failures speak plainly, Rerun makes a new job, Bengali is complete.
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import "../public/screens/jobs.js";
const J = globalThis.SPJobs;
const contract = JSON.parse(readFileSync(new URL("../../schemas/live-contract.json", import.meta.url), "utf8"));
const fx = n => JSON.parse(readFileSync(new URL(`../../tests/fixtures/live/routes/${n}.json`, import.meta.url), "utf8")).response;
const NOW = Date.parse("2026-11-25T10:00:00+05:30");
const mk = (kind, status, extra = {}) => ({ id: "j_" + kind + status, kind, payload: kind === "analyse" ? { symbol: "FIXA", exchange: "NSE" } : {}, asked_by: "system", status, result: status === "done" ? "Done" : null, error: status === "failed" ? "No model is available. Try again in about an hour." : null, error_bn: null, created_at: "2026-11-25T09:00:00+05:30", started_at: status === "queued" ? null : "2026-11-25T09:02:00+05:30", finished_at: status === "done" || status === "failed" ? "2026-11-25T09:10:00+05:30" : null, ...extra });
const kinds = Array.isArray(contract.job_kinds) ? contract.job_kinds.map(k => k.id || k.kind || k.name) : Object.keys(contract.job_kinds);

describe("jobs screen", () => {
  it("knows every job kind in the contract and names it in plain words", () => {
    for (const k of kinds) { expect(J.KINDS[k], k).toBeTruthy(); expect(J.words.kinds_bn[k], k).toMatch(/[ঀ-৿]/); }
  });
  it("renders a job of every kind in every state", () => {
    for (const status of ["queued", "running", "done", "failed"]) {
      const html = J.page({ jobs: kinds.map(k => mk(k, status)), lines: {}, budget: fx("budget_get") }, "en", NOW, "owner");
      for (const k of kinds) expect(html, `${k}/${status}`).toContain(J.KINDS[k][0]);
    }
  });
  it("shows progress lines in order and the Bengali line when asked", () => {
    const lines = [{ seq: 2, state: "info", text: "Second", text_bn: "দ্বিতীয়" }, { seq: 1, state: "ok", text: "First", text_bn: "প্রথম" }];
    const st = { jobs: [mk("analyse", "running")], lines: { j_analyserunning: lines } };
    const en = J.page(st, "en", NOW, "owner"), bn = J.page(st, "bn", NOW, "owner");
    expect(en.indexOf("First")).toBeLessThan(en.indexOf("Second"));
    expect(bn).toContain("প্রথম");
  });
  it("a failed job shows its plain error and a Rerun button only for the owner", () => {
    const st = { jobs: [mk("news_tag", "failed")] };
    expect(J.page(st, "en", NOW, "owner")).toContain("data-jn-rerun");
    expect(J.page(st, "en", NOW, "owner")).toContain("No model is available");
    expect(J.page(st, "en", NOW, "father")).not.toContain("data-jn-rerun");
  });
  it("never prints a stack trace for a failure with no words", () => {
    expect(J.failWords({ error: null }, "en")).toBe("Something went wrong. Try again.");
  });
  it("shows the write budget and counts minutes", () => {
    const html = J.page({ jobs: [mk("nightly", "done")], budget: fx("budget_get") }, "en", NOW, "owner");
    expect(html).toContain("18,000 of 85,000");
    expect(J.group([mk("nightly", "done")], NOW).minutes).toBe(8);
  });
  it("the father sees a polite note, not an error", () => {
    expect(J.page({ denied: true }, "en", NOW, "father")).toContain("Only the owner");
  });
  it("Bengali table has every English word", () => {
    expect(Object.keys(J.words.en).filter(k => !(k in J.words.bn))).toEqual([]);
  });
  it("escapes what the server sends", () => {
    expect(J.page({ jobs: [mk("analyse", "failed", { error: "<img src=x onerror=1>" })] }, "en", NOW, "owner")).not.toContain("<img");
  });
});

describe("jobs loading and rerun", () => {
  const server = () => {
    const s = { calls: [], jobs: [mk("news_tag", "failed"), mk("analyse", "running")] };
    s.fetch = async (url, o = {}) => {
      s.calls.push([o.method || "GET", url]);
      const ok = b => ({ ok: true, status: 200, json: async () => b });
      if (url.endsWith("/rerun")) { s.jobs.unshift(mk("news_tag", "queued", { id: "new1" })); return ok({ id: "new1", status: "queued" }); }
      if (url.startsWith("/api/v2/jobs?")) return ok({ jobs: s.jobs });
      if (url.startsWith("/api/v2/budget")) return ok(fx("budget_get"));
      if (url.startsWith("/api/v2/jobs/")) return ok({ job: s.jobs[1], lines: [{ seq: 1, state: "info", text: "Working", text_bn: null }] });
      return { ok: false, status: 404, json: async () => ({}) };
    };
    return s;
  };
  it("loads jobs, budget and the lines of running jobs", async () => {
    const s = server(); await J.load(s.fetch, () => {});
    expect(J.state.jobs.length).toBe(2); expect(J.state.budget.writes).toBe(18000); expect(J.state.lines.j_analyserunning.length).toBe(1);
  });
  it("Rerun posts to the rerun route and the list then holds a new job", async () => {
    const s = server(); await J.load(s.fetch, () => {}); await J.rerun(s.fetch, "j_news_tagfailed", () => {});
    expect(s.calls).toContainEqual(["POST", "/api/v2/jobs/j_news_tagfailed/rerun"]);
    expect(J.state.jobs.some(j => j.id === "new1" && j.status === "queued")).toBe(true);
  });
  it("a 403 means denied, a network failure means offline", async () => {
    await J.load(async () => ({ ok: false, status: 403, json: async () => ({}) }), () => {}); expect(J.state.denied).toBe(true);
    await J.load(async () => { throw new Error("x"); }, () => {}); expect(J.state.offline).toBe(true);
  });
});
