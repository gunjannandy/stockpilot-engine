import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { FakeKV, ctx } from "./helpers.js";
import { onRequestGet as listMine, onRequestPost as post } from "../functions/api/queue/index.js";
import { onRequestDelete as undo } from "../functions/api/queue/[id].js";
import { onRequestGet as vmList } from "../functions/api/vm/queue/index.js";
import { onRequestPost as ack } from "../functions/api/vm/queue/ack.js";
import { onRequestGet as me } from "../functions/api/me.js";

const O = "https://sp.test";
const env = () => ({ SP: new FakeKV() });
const send = (e, kind, payload, person = "father") =>
  post(ctx(`${O}/api/queue`, e, { data: { person }, init: { method: "POST", body: JSON.stringify({ kind, payload }) } }));

describe("queue", () => {
  it("POST records who and when; the VM sees it with by and at", async () => {
    const e = env();
    const r = await send(e, "watchlist_add", { symbol: "SBIN", exchange: "NSE" });
    const { id } = await r.json();
    expect(id).toBeTruthy();
    const items = await (await vmList(ctx(`${O}/api/vm/queue`, e))).json();
    expect(items).toHaveLength(1);
    expect(items[0]).toMatchObject({ id, kind: "watchlist_add", payload: { symbol: "SBIN", exchange: "NSE" }, by: "father" });
    expect(Date.parse(items[0].at)).not.toBeNaN();
    expect(Object.keys(items[0]).sort()).toEqual(["at", "by", "id", "kind", "payload"]);
  });

  it("rejects unknown kinds, bad bodies, and anonymous callers", async () => {
    const e = env();
    expect((await send(e, "place_order", {})).status).toBe(400);
    expect((await post(ctx(`${O}/api/queue`, e, { data: { person: "father" }, init: { method: "POST", body: "nope" } }))).status).toBe(400);
    expect((await send(e, "rerun", {}, null)).status).toBe(401);
    expect([...e.SP.m.keys()].filter((k) => k.startsWith("q:"))).toEqual([]);
  });

  it("?after= returns only newer requests, in order", async () => {
    const e = env();
    const a = (await (await send(e, "rerun", {})).json()).id;
    await new Promise((r) => setTimeout(r, 3));
    const b = (await (await send(e, "refresh_docs", {})).json()).id;
    const after = await (await vmList(ctx(`${O}/api/vm/queue?after=${a}`, e))).json();
    expect(after.map((i) => i.id)).toEqual([b]);
  });

  it("undo works until the VM takes the request, then is refused", async () => {
    const e = env();
    const a = (await (await send(e, "rerun", {})).json()).id;
    const b = (await (await send(e, "refresh_docs", {})).json()).id;
    expect((await undo(ctx(`${O}/api/queue/${a}`, e, { params: { id: a } }))).status).toBe(200);
    expect(await e.SP.get(`q:${a}`)).toBeNull();
    await vmList(ctx(`${O}/api/vm/queue`, e));
    const late = await undo(ctx(`${O}/api/queue/${b}`, e, { params: { id: b } }));
    expect(late.status).toBe(409);
    expect(await e.SP.get(`q:${b}`)).not.toBeNull();
    expect((await undo(ctx(`${O}/api/queue/zzz`, e, { params: { id: "zzz" } }))).status).toBe(404);
  });

  it("ack records done or failed with a note, and the page sees it", async () => {
    const e = env();
    const id = (await (await send(e, "budget_set", { month: "2026-12", amount_inr: 1 })).json()).id;
    const bad = await ack(ctx(`${O}/api/vm/queue/ack`, e, { init: { method: "POST", body: JSON.stringify({ id, status: "maybe" }) } }));
    expect(bad.status).toBe(400);
    const ok = await ack(ctx(`${O}/api/vm/queue/ack`, e, { init: { method: "POST", body: JSON.stringify({ id, status: "failed", note: "Month must look like 2026-12." }) } }));
    expect(ok.status).toBe(200);
    const { items } = await (await listMine(ctx(`${O}/api/queue`, e))).json();
    expect(items[0]).toMatchObject({ id, status: "failed", note: "Month must look like 2026-12.", by: "father" });
    expect((await ack(ctx(`${O}/api/vm/queue/ack`, e, { init: { method: "POST", body: JSON.stringify({ id: "nope", status: "done" }) } }))).status).toBe(404);
    // acked requests are not handed to the VM again
    expect(await (await vmList(ctx(`${O}/api/vm/queue`, e))).json()).toEqual([]);
  });

  it("a taken but unacked request shows as taken", async () => {
    const e = env();
    await send(e, "rerun", {});
    await vmList(ctx(`${O}/api/vm/queue`, e));
    const { items } = await (await listMine(ctx(`${O}/api/queue`, e))).json();
    expect(items[0].status).toBe("taken");
  });

  it("/api/me names the person", async () => {
    expect(await (await me({ data: { person: "owner" } })).json()).toEqual({ person: "owner" });
  });
});

describe("queue kinds file", () => {
  it("lists every kind the VM handles, and the Worker accepts each", async () => {
    const { readFileSync } = await import("node:fs");
    const spec = JSON.parse(readFileSync(new URL("../../schemas/queue-kinds.json", import.meta.url), "utf8"));
    const { KINDS } = await import("../lib/queue.js");
    expect([...KINDS].sort()).toEqual(Object.keys(spec.kinds).sort());
    for (const kind of ["not_now", "not_now_undo", "feedback", "feedback_decide", "learned_forget"]) expect(KINDS).toContain(kind);
    const e = env();
    expect((await send(e, "not_now", { symbol: "SBIN", scope: "buy", for: "week" })).status).toBe(200);
    expect((await send(e, "not_now_undo", { id: 1 })).status).toBe(200);
  });
});

describe("lane W kinds", () => {
  // 2026-11-24 12:00 IST = 06:30 UTC
  const at = (iso) => vi.setSystemTime(new Date(iso));
  const noon = "2026-11-24T06:30:00Z";
  beforeEach(() => vi.useFakeTimers({ toFake: ["Date"] }));
  afterEach(() => vi.useRealTimers());

  it("long_term_mark is accepted for both on and off and reaches the VM with its payload", async () => {
    const e = env(); at(noon);
    expect((await send(e, "long_term_mark", { symbol: "JIOFIN", on: true })).status).toBe(200);
    vi.advanceTimersByTime(5);
    expect((await send(e, "long_term_mark", { symbol: "JIOFIN", on: false })).status).toBe(200);
    const items = await (await vmList(ctx(`${O}/api/vm/queue`, e))).json();
    expect(items.map((i) => [i.kind, i.payload.on])).toEqual([["long_term_mark", true], ["long_term_mark", false]]);
  });

  it("ask_analyst: five a day, the sixth gets 429 and is not queued", async () => {
    const e = env(); at(noon);
    for (const s of ["A", "B", "C", "D", "E"]) {
      vi.advanceTimersByTime(5);
      expect((await send(e, "ask_analyst", { symbol: s })).status).toBe(200);
    }
    const over = await send(e, "ask_analyst", { symbol: "F" });
    expect(over.status).toBe(429);
    expect((await over.json()).error).toMatch(/5/);
    expect((await listMine(ctx(`${O}/api/queue`, e))).status).toBe(200);
    const { items } = await (await listMine(ctx(`${O}/api/queue`, e))).json();
    expect(items.filter((i) => i.kind === "ask_analyst")).toHaveLength(5);
  });

  it("ask_analyst: the cap resets on the next IST day, and other kinds are never capped", async () => {
    const e = env(); at(noon);
    for (const s of ["A", "B", "C", "D", "E"]) { vi.advanceTimersByTime(5); await send(e, "ask_analyst", { symbol: s }); }
    for (let i = 0; i < 8; i++) { vi.advanceTimersByTime(5); expect((await send(e, "watchlist_add", { symbol: "X" + i })).status).toBe(200); }
    // 23:30 IST on the 24th is still the same day: capped
    at("2026-11-24T18:00:00Z");   // 23:30 IST
    expect((await send(e, "ask_analyst", { symbol: "G" })).status).toBe(429);
    at("2026-11-24T18:31:00Z");   // 00:01 IST on the 25th
    expect((await send(e, "ask_analyst", { symbol: "G" })).status).toBe(200);
  });

  it("ask_analyst: undoing a request gives the slot back", async () => {
    const e = env(); at(noon);
    const ids = [];
    for (const s of ["A", "B", "C", "D", "E"]) { vi.advanceTimersByTime(5); ids.push((await (await send(e, "ask_analyst", { symbol: s })).json()).id); }
    await undo(ctx(`${O}/api/queue/${ids[0]}`, e, { params: { id: ids[0] } }));
    expect((await send(e, "ask_analyst", { symbol: "F" })).status).toBe(200);
  });

  it("ask_analyst: refused 19:00 to 22:00 IST (the nightly run), open at 18:59 and 22:00", async () => {
    const e = env();
    at("2026-11-24T13:29:00Z");   // 18:59 IST
    expect((await send(e, "ask_analyst", { symbol: "A" })).status).toBe(200);
    at("2026-11-24T13:30:00Z");   // 19:00 IST
    const shut = await send(e, "ask_analyst", { symbol: "B" });
    expect(shut.status).toBe(429);
    expect((await shut.json()).error).toMatch(/22:00|evening|tonight/i);
    at("2026-11-24T16:29:00Z");   // 21:59 IST
    expect((await send(e, "ask_analyst", { symbol: "B" })).status).toBe(429);
    at("2026-11-24T16:30:00Z");   // 22:00 IST
    expect((await send(e, "ask_analyst", { symbol: "B" })).status).toBe(200);
  });

  it("ask_analyst needs a symbol", async () => {
    const e = env(); at(noon);
    expect((await send(e, "ask_analyst", {})).status).toBe(400);
    expect((await send(e, "long_term_mark", { symbol: "TCS" })).status).toBe(400);   // `on` is missing
    expect([...e.SP.m.keys()].filter((k) => k.startsWith("q:"))).toEqual([]);
  });

  it("the kinds file lists both new kinds with their keys", async () => {
    const { PAYLOAD_KEYS } = await import("../lib/queue.js");
    expect(PAYLOAD_KEYS.long_term_mark).toEqual(["symbol", "on"]);
    expect(PAYLOAD_KEYS.ask_analyst).toEqual(["symbol"]);
  });
});

describe("retiring the KV queue (#114)", () => {
  it("every call to /api/queue leaves a last-call stamp, and the VM can read it with the pending count", async () => {
    const { onRequestGet: status } = await import("../functions/api/vm/queue/status.js");
    const e = env();
    expect(await (await status(ctx(`${O}/api/vm/queue/status`, e))).json()).toEqual({ last_call_at: null, pending: 0 });
    await send(e, "rerun", { job: "kite" });
    await listMine(ctx(`${O}/api/queue`, e));
    const got = await (await status(ctx(`${O}/api/vm/queue/status`, e))).json();
    expect(Date.parse(got.last_call_at)).not.toBeNaN();
    expect(got.pending).toBe(1);
  });
});
