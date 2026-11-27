// V2: the page follows the Sync job after the Kite login.
import { describe, it, expect } from "vitest";
import "../public/screens/sync.js";
const S = globalThis.SPSync;
const job = (status, extra = {}) => ({ id: "j1", kind: "sync", status, result: null, error: null, error_bn: null, ...extra });
const line = (seq, text, state = "info") => ({ job_id: "j1", seq, state, text, text_bn: "বাং " + text });

describe("sync follow", () => {
  it("shows steps as they arrive and ends with the change count", async () => {
    const steps = [{ job: job("queued"), lines: [] },
      { job: job("running"), lines: [line(1, "Checking Kite login"), line(2, "Logged in, holdings fetched")] },
      { job: job("done", { result: "Done, 3 changes" }), lines: [line(1, "Checking Kite login"), line(2, "Logged in, holdings fetched"), line(3, "Done, 3 changes", "ok")] }];
    const seen = []; let i = 0;
    const last = await S.follow("j1", { fetch: async () => steps[i++], onState: s => seen.push(S.html(s, "en")), sleep: async () => {}, now: () => 0 });
    expect(i).toBe(3);
    expect(last.job.status).toBe("done");
    expect(seen[0]).toContain("Waiting for the VM");
    expect(seen[1]).toContain("Logged in, holdings fetched");
    expect(seen[2]).toContain("Done, 3 changes");
  });
  it("a failed job shows its plain error, in Bengali when asked", () => {
    const s = { job: job("failed", { error: "No Kite login today.", error_bn: "আজ লগইন নেই" }), lines: [line(1, "Checking Kite login", "fail")] };
    expect(S.html(s, "en")).toContain("No Kite login today.");
    expect(S.html(s, "bn")).toContain("আজ লগইন নেই");
    expect(S.html(s, "bn")).toContain("বাং Checking Kite login");
  });
  it("keeps polling through a network blip", async () => {
    let n = 0;
    const last = await S.follow("j1", { fetch: async () => { if (n++ === 0) throw new Error("offline"); return { job: job("done", { result: "Done, no changes" }), lines: [] }; }, onState: () => {}, sleep: async () => {}, now: () => 0 });
    expect(last.job.result).toBe("Done, no changes");
  });
});
