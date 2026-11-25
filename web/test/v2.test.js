// Every v2 route in schemas/live-contract.json, run against a local D1 holding the T0 fixture rows.
import { beforeEach, describe, expect, it } from "vitest";
import { localD1, problems, route, CONTRACT } from "./d1.js";
import * as v2 from "../lib/v2/handlers.js";
import { onRequest as middleware } from "../functions/_middleware.js";

const O = "https://sp.test";
const NOW = new Date("2026-11-25T10:00:00+05:30");
const PEOPLE = JSON.stringify({ owner: "o@example.test", father: "f@example.test" });
let env;
beforeEach(() => { env = { DB: localD1(), SP_PEOPLE: PEOPLE, SP_INGEST_KEY: "ingest-key-0123456789" }; });

// person: "owner" is the owner, "father" the father (SP_PEOPLE ids; SP_OWNER defaults to owner).
const call = async (fn, path, { person = "owner", method = "GET", body, params = {}, headers = {}, extra = {} } = {}) => {
  const init = { method, headers, ...(body === undefined ? {} : { body: JSON.stringify(body) }) };
  const res = await fn({ request: new Request(O + path, init), env, data: { person }, params, now: NOW, ...extra });
  return { status: res.status, body: await res.json().catch(() => null), res };
};
const ok = (id, body) => expect(problems(body, route(id).response), id).toEqual([]);

describe("jobs", () => {
  it("jobs_create queues a job for the asker and the page can poll it", async () => {
    const r = await call(v2.jobsCreate, "/api/v2/jobs", { method: "POST", person: "father", body: { kind: "analyse", payload: { symbol: "FIXC", exchange: "NSE" } } });
    expect(r.status).toBe(200); ok("jobs_create", r.body);
    expect(r.body.status).toBe("queued");
    const got = await call(v2.jobsGet, `/api/v2/jobs/${r.body.id}`, { person: "father", params: { id: r.body.id } });
    expect(got.body.job).toMatchObject({ kind: "analyse", asked_by: "father", status: "queued", payload: { symbol: "FIXC", exchange: "NSE" } });
    expect(got.body.lines).toEqual([]);
  });
  it("jobs_create refuses unknown kinds, wrong payload keys and anonymous callers", async () => {
    const bad = (body, person = "owner") => call(v2.jobsCreate, "/api/v2/jobs", { method: "POST", person, body });
    expect((await bad({ kind: "place_order", payload: {} })).status).toBe(400);
    expect((await bad({ kind: "analyse", payload: { symbol: "FIXC" } })).status).toBe(400);
    expect((await bad({ kind: "analyse", payload: { symbol: "FIXC", exchange: "NSE", extra: 1 } })).status).toBe(400);
    expect((await bad({ kind: "sync" })).status).toBe(200); // no payload means {}
    expect((await bad({ kind: "sync", payload: {} }, null)).status).toBe(401);
    expect((await bad({ kind: "sync", payload: {} }, "stranger")).status).toBe(401);
  });
  it("jobs_get returns lines in seq order and 404 for an unknown job", async () => {
    const r = await call(v2.jobsGet, "/api/v2/jobs/job_001", { params: { id: "job_001" } });
    ok("jobs_get", r.body);
    expect(r.body.lines.map((l) => l.seq)).toEqual([...r.body.lines.map((l) => l.seq)].sort((a, b) => a - b));
    expect((await call(v2.jobsGet, "/api/v2/jobs/nope", { params: { id: "nope" } })).status).toBe(404);
  });
  it("jobs_list is for the owner only and filters by status and limit", async () => {
    const all = await call(v2.jobsList, "/api/v2/jobs");
    ok("jobs_list", all.body);
    expect(all.body.jobs.length).toBeGreaterThan(1);
    const failed = await call(v2.jobsList, "/api/v2/jobs?status=failed");
    expect(failed.body.jobs.every((j) => j.status === "failed")).toBe(true);
    expect((await call(v2.jobsList, "/api/v2/jobs?limit=1")).body.jobs).toHaveLength(1);
    expect((await call(v2.jobsList, "/api/v2/jobs", { person: "father" })).status).toBe(403);
  });
  it("jobs_rerun copies a failed job into a new queued job, owner only", async () => {
    const failed = (await call(v2.jobsList, "/api/v2/jobs?status=failed")).body.jobs[0];
    expect((await call(v2.jobsRerun, `/api/v2/jobs/${failed.id}/rerun`, { method: "POST", person: "father", params: { id: failed.id } })).status).toBe(403);
    const r = await call(v2.jobsRerun, `/api/v2/jobs/${failed.id}/rerun`, { method: "POST", params: { id: failed.id } });
    expect(r.status).toBe(200); ok("jobs_rerun", r.body);
    const again = (await call(v2.jobsGet, "", { params: { id: r.body.id } })).body.job;
    expect(again).toMatchObject({ kind: failed.kind, payload: failed.payload, status: "queued", asked_by: "owner" });
    expect((await call(v2.jobsRerun, "", { method: "POST", params: { id: "job_001" } })).status).toBe(409); // a done job is not rerun
    expect((await call(v2.jobsRerun, "", { method: "POST", params: { id: "nope" } })).status).toBe(404);
  });
});

describe("marks (changes)", () => {
  it("changes_list shows only the signed-in person's marks", async () => {
    const dad = await call(v2.changesList, "/api/v2/changes", { person: "father" });
    ok("changes_list", dad.body);
    expect(dad.body.person).toBe("father");
    expect(dad.body.items.every((c) => c.person === "father")).toBe(true);
    expect(dad.body.unseen_count).toBe(dad.body.items.filter((c) => !c.seen_at).length);
    const me = await call(v2.changesList, "/api/v2/changes");
    expect(me.body.person).toBe("owner");
    expect(me.body.items.every((c) => c.person === "owner")).toBe(true);
  });
  it("the owner's visit does not clear the father's marks", async () => {
    const before = (await call(v2.changesList, "/api/v2/changes", { person: "father" })).body.unseen_count;
    expect(before).toBeGreaterThan(0);
    await call(v2.changesSeen, "/api/v2/changes/seen", { method: "POST", body: { all: true } }); // owner
    expect((await call(v2.changesList, "/api/v2/changes", { person: "father" })).body.unseen_count).toBe(before);
    expect((await call(v2.changesList, "/api/v2/changes")).body.unseen_count).toBe(0);
  });
  it("changes_seen clears by symbol, by ids or all, and says how many", async () => {
    const r = await call(v2.changesSeen, "/api/v2/changes/seen", { method: "POST", person: "father", body: { symbol: "FIXA" } });
    expect(r.status).toBe(200); ok("changes_seen", r.body);
    expect(r.body.marked).toBe(1);
    expect((await call(v2.changesSeen, "", { method: "POST", person: "father", body: { symbol: "FIXA" } })).body.marked).toBe(0);
    const owners = (await call(v2.changesList, "/api/v2/changes", { person: "father" })).body.items;
    // ids belonging to another person are never touched
    const mine = await call(v2.changesSeen, "", { method: "POST", person: "owner", body: { ids: owners.map((c) => c.id) } });
    expect(mine.body.marked).toBe(0);
    expect((await call(v2.changesSeen, "", { method: "POST", body: {} })).status).toBe(400);
  });
  it("changes older than 7 days leave the strip but stay in the stock's history", async () => {
    env.DB.db.prepare("insert into changes (id,person,symbol,kind,reason,at) values ('old1','father','FIXA','call_changed','old','2026-11-10T09:00:00+05:30')").run();
    const list = await call(v2.changesList, "/api/v2/changes", { person: "father" });
    expect(list.body.items.find((c) => c.id === "old1")).toBeUndefined();
    const one = await call(v2.callGet, "/api/v2/calls/FIXA", { person: "father", params: { symbol: "FIXA" } });
    expect(one.body.changes.find((c) => c.id === "old1")).toBeTruthy();
  });
});

describe("stocks", () => {
  it("call_get returns the call with booleans and the form parsed, and this person's changes", async () => {
    const r = await call(v2.callGet, "/api/v2/calls/FIXA", { person: "father", params: { symbol: "FIXA" } });
    expect(r.status).toBe(200); ok("call_get", r.body);
    expect(typeof r.body.call.out_of_date).toBe("boolean");
    expect(r.body.changes.every((c) => c.person === "father")).toBe(true);
    expect((await call(v2.callGet, "", { params: { symbol: "NOPE" } })).status).toBe(404);
  });
  it("lists_get returns members by rank, with call null for No forecast yet", async () => {
    const names = [...new Set(env.DB.db.prepare("select list_name from lists").all().map((r) => r.list_name))];
    expect(names.length).toBeGreaterThan(0);
    const r = await call(v2.listsGet, `/api/v2/lists/${names[0]}`, { params: { name: names[0] } });
    expect(r.status).toBe(200); ok("lists_get", r.body);
    expect(r.body.items.map((i) => i.rank)).toEqual([...r.body.items.map((i) => i.rank)].sort((a, b) => a - b));
    env.DB.db.prepare("insert into lists (list_name,symbol,exchange,rank,reason,since) values (?, 'FIXD','NSE',99,'x','2026-11-25T09:00:00+05:30')").run(names[0]);
    env.DB.db.prepare("delete from calls where symbol='FIXD'").run();
    const again = await call(v2.listsGet, "", { params: { name: names[0] } });
    expect(again.body.items.find((i) => i.symbol === "FIXD")).toMatchObject({ call: null, out_of_date: false });
  });
  it("quotes_get returns the asked symbols with their age", async () => {
    const r = await call(v2.quotesGet, "/api/v2/quotes?symbols=FIXA,FIXB,NOPE");
    ok("quotes_get", r.body);
    expect(r.body.quotes.every((q) => ["FIXA", "FIXB"].includes(q.symbol))).toBe(true);
    for (const q of r.body.quotes) expect(q.age_seconds).toBe(Math.max(0, Math.floor((NOW - new Date(q.as_of)) / 1000)));
    expect((await call(v2.quotesGet, "/api/v2/quotes")).body.quotes).toEqual([]);
  });
});

describe("news", () => {
  it("news_list ranks high tier first, with tags, rank and sector mood", async () => {
    const r = await call(v2.newsList, "/api/v2/news?limit=10");
    expect(r.status).toBe(200); ok("news_list", r.body);
    expect(r.body.items.length).toBeGreaterThan(0);
    const scores = r.body.items.map((i) => i.rank.score);
    expect(scores).toEqual([...scores].sort((a, b) => b - a));
    expect((await call(v2.newsList, "/api/v2/news?limit=1")).body.items).toHaveLength(1);
  });
  it("news_list shows an unranked item as low, not hidden", async () => {
    env.DB.db.prepare("insert into news_items (id,link,title,source,published_at,group_id,source_count,market_wide,direction,impact) values ('n_new','https://news.example.test/x','Plain','Wire','2026-11-25T09:50:00+05:30','g_new',1,0,'none',1)").run();
    const item = (await call(v2.newsList, "/api/v2/news?limit=100")).body.items.find((i) => i.id === "n_new");
    expect(item.rank).toMatchObject({ tier: "low", closeness: "other", score: 0 });
  });
  it("og_image reads og:image from the article page, edge cached 7 days, and refuses private hosts", async () => {
    const fetcher = async (u) => new Response(`<html><head><meta property="og:image" content="https://img.example.test/a.jpg"><link rel="icon" href="/f.png"></head></html>`, { headers: { "content-type": "text/html" } });
    const r = await call(v2.ogImage, "/api/v2/og?url=" + encodeURIComponent("https://news.example.test/a"), { extra: { fetch: fetcher } });
    ok("og_image", r.body);
    expect(r.body).toEqual({ image: "https://img.example.test/a.jpg", logo: "https://news.example.test/f.png" });
    expect(r.res.headers.get("Cache-Control")).toContain("max-age=604800");
    for (const u of ["http://localhost/x", "http://127.0.0.1/x", "http://192.168.1.1/x", "ftp://a.test/x", "nonsense"]) {
      expect((await call(v2.ogImage, "/api/v2/og?url=" + encodeURIComponent(u), { extra: { fetch: fetcher } })).status).toBe(400);
    }
    const down = await call(v2.ogImage, "/api/v2/og?url=" + encodeURIComponent("https://news.example.test/b"), { extra: { fetch: async () => { throw new Error("down"); } } });
    expect(down.body).toEqual({ image: null, logo: null });
  });
});

describe("og_image: cheap, cached, publisher-only", () => {
  const OG = (u, extra = {}) => "/api/v2/og?url=" + encodeURIComponent(u) + extra.query;
  const html = (head) => `<html><head>${head}</head><body>x</body></html>`;
  const cache = () => { const m = new Map(); return { m, match: async (r) => m.get(r.url)?.clone(), put: async (r, res) => { m.set(r.url, res.clone()); } }; };
  const streamOf = (text, onPull) => { const bytes = new TextEncoder().encode(text); let i = 0; return new ReadableStream({ pull(c) { if (i >= bytes.length) return c.close(); const n = Math.min(8192, bytes.length - i); c.enqueue(bytes.slice(i, i + n)); i += n; onPull?.(i); } }); };
  const get = (url, extra, query = "") => call(v2.ogImage, OG(url, { query }), { extra });

  it("reads at most the first 100 KB: a tag after that is not seen, and the rest is never pulled", async () => {
    let pulled = 0;
    const page = html('<script>' + "a".repeat(150_000) + '</script><meta property="og:image" content="https://img.example.test/late.jpg">');
    const fetcher = async () => new Response(streamOf(page, (n) => { pulled = n; }), { headers: { "content-type": "text/html" } });
    const r = await get("https://news.example.test/late", { fetch: fetcher, cache: cache() });
    expect(r.body.image).toBeNull();
    expect(pulled).toBeLessThanOrEqual(102_400 + 2 * 8192); // one chunk over the limit plus the stream's own prefetch; the other 50 KB is never pulled
  });
  it("stops at the end of <head>", async () => {
    let pulled = 0;
    const page = html('<meta property="og:image" content="/p.jpg">') + "b".repeat(90_000);
    const fetcher = async () => new Response(streamOf(page, (n) => { pulled = n; }));
    const r = await get("https://news.example.test/a", { fetch: fetcher, cache: cache() });
    expect(r.body.image).toBe("https://news.example.test/p.jpg");
    expect(pulled).toBeLessThanOrEqual(3 * 8192); // streams prefetch a chunk; 90 KB of body is never read
  });
  it("a second view of the same card comes from cache and does not fetch the publisher again", async () => {
    let calls = 0; const c = cache();
    const fetcher = async () => { calls++; return new Response(html('<meta property="og:image" content="https://img.example.test/a.jpg">')); };
    const first = await get("https://news.example.test/a#frag", { fetch: fetcher, cache: c });
    const second = await get("https://news.example.test/a", { fetch: fetcher, cache: c, person: "papa" });
    expect(calls).toBe(1);
    expect(second.body).toEqual(first.body);
    expect(first.res.headers.get("Cache-Control")).toContain("max-age=604800");
  });
  it("a signed-out caller never reaches the cache", async () => {
    const c = cache(); c.m.set(O + "/api/v2/og?url=" + encodeURIComponent("https://news.example.test/a"), new Response("{}"));
    expect((await call(v2.ogImage, OG("https://news.example.test/a", { query: "" }), { person: null, extra: { cache: c } })).status).toBe(401);
  });
  it("a failure is answered empty and is not kept for 7 days", async () => {
    const c = cache();
    const r = await get("https://news.example.test/b", { fetch: async () => { throw new Error("down"); }, cache: c });
    expect(r.body).toEqual({ image: null, logo: null });
    expect(r.res.headers.get("Cache-Control")).not.toContain("604800");
  });
  it("a redirect to a private address is refused", async () => {
    let hops = 0;
    const fetcher = async (u) => { hops++; return new Response(null, { status: 302, headers: { Location: "http://169.254.169.254/latest" } }); };
    const r = await get("https://news.example.test/r", { fetch: fetcher, cache: cache() });
    expect(r.body).toEqual({ image: null, logo: null });
    expect(hops).toBe(1);
  });
  it("a public redirect is followed", async () => {
    const fetcher = async (u) => u.includes("/old") ? new Response(null, { status: 301, headers: { Location: "https://news.example.test/new" } }) : new Response(html('<meta property="og:image" content="/n.jpg">'));
    expect((await get("https://news.example.test/old", { fetch: fetcher, cache: cache() })).body.image).toBe("https://news.example.test/n.jpg");
  });
  it("a page full of unclosed tags costs little CPU (free plan: 10 ms)", async () => {
    const page = "<html><head><script>" + "a".repeat(60_000) + "</script>" + "<meta ".repeat(3000) + '<meta property="og:image" content="/x.jpg">';
    const times = [];
    for (let i = 0; i < 15; i++) {
      const t = process.cpuUsage();
      await get("https://news.example.test/p" + i, { fetch: async () => new Response(page), cache: cache() });
      const d = process.cpuUsage(t); times.push((d.user + d.system) / 1000);
    }
    times.sort((a, b) => a - b);
    expect(times[7]).toBeLessThan(10);
  });
  it("Google News links are not fetched; the card shows the publisher's logo when told the publisher", async () => {
    let calls = 0; const fetcher = async () => { calls++; return new Response(""); };
    const g = "https://news.google.com/rss/articles/CBMi123";
    const withSite = await get(g, { fetch: fetcher, cache: cache() }, "&site=" + encodeURIComponent("https://www.livemint.com/markets"));
    expect(withSite.body).toEqual({ image: null, logo: "https://www.livemint.com/favicon.ico" });
    const without = await get(g, { fetch: fetcher, cache: cache() });
    expect(without.body).toEqual({ image: null, logo: null });
    const bad = await get(g, { fetch: fetcher, cache: cache() }, "&site=" + encodeURIComponent("http://localhost/x"));
    expect(bad.body.logo).toBeNull();
    expect(calls).toBe(0);
  });
});

describe("feedback and asks", () => {
  it("feedback_create shows at once as received, and only its author sees it", async () => {
    const r = await call(v2.feedbackCreate, "/api/v2/feedback", { method: "POST", person: "father", body: { text: "  chart ta boro koro  " } });
    expect(r.status).toBe(200); ok("feedback_create", r.body);
    const dad = await call(v2.feedbackList, "/api/v2/feedback", { person: "father" });
    ok("feedback_list", dad.body);
    expect(dad.body.items.find((f) => f.id === r.body.id)).toMatchObject({ text: "chart ta boro koro", status: "received", asks: [] });
    expect((await call(v2.feedbackList, "/api/v2/feedback")).body.items.find((f) => f.id === r.body.id)).toBeUndefined();
    expect((await call(v2.feedbackCreate, "", { method: "POST", body: { text: "   " } })).status).toBe(400);
  });
  it("feedback_create also queues the job that reads it", async () => {
    const r = await call(v2.feedbackCreate, "/api/v2/feedback", { method: "POST", person: "father", body: { text: "hello" } });
    const job = env.DB.db.prepare("select * from jobs where kind='feedback_read' order by created_at desc, id desc limit 1").get();
    expect(JSON.parse(job.payload)).toEqual({ feedback_id: r.body.id });
    expect(job.status).toBe("queued");
  });
  it("ask_not_meant flags an ask of the person's own feedback only", async () => {
    const asks = env.DB.db.prepare("select a.id, f.person from asks a join feedback f on f.id = a.feedback_id").all();
    const a = asks[0], me = a.person === "owner" ? "owner" : "father", other = a.person === "owner" ? "father" : "owner";
    expect((await call(v2.askNotMeant, "", { method: "POST", person: other, params: { id: a.id } })).status).toBe(404);
    const r = await call(v2.askNotMeant, "", { method: "POST", person: me, params: { id: a.id } });
    expect(r.status).toBe(200); ok("ask_not_meant", r.body);
    expect(r.body.not_meant).toBe(true);
  });
  it("only the owner can Approve or Decline, and only an ask that waits", async () => {
    const wait = env.DB.db.prepare("select id from asks where status='waiting_for_approval'").get().id;
    const dad = await call(v2.askDecide, "", { method: "POST", person: "father", params: { id: wait }, body: { decision: "approve" } });
    expect(dad.status).toBe(403);
    expect(env.DB.db.prepare("select status from asks where id=?").get(wait).status).toBe("waiting_for_approval");
    expect((await call(v2.askDecide, "", { method: "POST", person: null, params: { id: wait }, body: { decision: "approve" } })).status).toBe(401);
    expect((await call(v2.askDecide, "", { method: "POST", params: { id: wait }, body: { decision: "maybe" } })).status).toBe(400);
    const r = await call(v2.askDecide, "", { method: "POST", params: { id: wait }, body: { decision: "approve" } });
    expect(r.status).toBe(200); ok("ask_decide", r.body);
    expect(r.body.status).toBe("being_built");
    expect((await call(v2.askDecide, "", { method: "POST", params: { id: wait }, body: { decision: "decline" } })).status).toBe(409);
  });
  it("a decision gives the feedback's author a yellow mark, and decline says declined", async () => {
    const wait = env.DB.db.prepare("select a.id, f.person from asks a join feedback f on f.id=a.feedback_id where a.status='waiting_for_approval'").get();
    const before = env.DB.db.prepare("select count(*) n from changes where person=? and kind='ask_status'").get(wait.person).n;
    const r = await call(v2.askDecide, "", { method: "POST", params: { id: wait.id }, body: { decision: "decline" } });
    expect(r.body.status).toBe("declined");
    expect(env.DB.db.prepare("select count(*) n from changes where person=? and kind='ask_status'").get(wait.person).n).toBe(before + 1);
  });
});

describe("operations", () => {
  it("budget_get is owner only and reports ok, warn or stopped", async () => {
    const r = await call(v2.budgetGet, "/api/v2/budget");
    expect(r.status).toBe(200); ok("budget_get", r.body);
    expect(r.body).toMatchObject({ day: "2026-11-25", warn_at: 60000, stop_at: 85000 });
    expect((await call(v2.budgetGet, "", { person: "father" })).status).toBe(403);
    env.DB.db.prepare("update write_budget set writes=61000 where day='2026-11-25'").run();
    expect((await call(v2.budgetGet, "")).body.status).toBe("warn");
    env.DB.db.prepare("update write_budget set writes=85000 where day='2026-11-25'").run();
    expect((await call(v2.budgetGet, "")).body.status).toBe("stopped");
  });
  it("budget_get on a day with no counter starts at zero", async () => {
    env.DB.db.prepare("delete from write_budget").run();
    expect((await call(v2.budgetGet, "")).body).toMatchObject({ writes: 0, status: "ok" });
  });
  const quote = { symbol: "FIXD", exchange: "NSE", price: 10, prev_close: 9, as_of: "2026-11-25T09:59:00+05:30", source: "yahoo" };
  const ingest = (body, key = "ingest-key-0123456789") => call(v2.ingestWrite, "/api/v2/ingest", { method: "POST", person: null, headers: { "X-SP-Ingest-Key": key }, body });
  it("ingest_write needs the key, writes public tables only and counts the rows it wrote", async () => {
    const before = env.DB.db.prepare("select writes from write_budget where day='2026-11-25'").get()?.writes ?? 0;
    const r = await ingest({ table: "quotes", rows: [quote] });
    expect(r.status).toBe(200); ok("ingest_write", r.body);
    expect(r.body).toMatchObject({ written: 1, stopped: false });
    expect(r.body.writes_today).toBeGreaterThan(before);
    expect(env.DB.db.prepare("select price from quotes where symbol='FIXD'").get().price).toBe(10);
    expect((await ingest({ table: "quotes", rows: [{ ...quote, price: 11 }] })).status).toBe(200); // same key replaces
    expect(env.DB.db.prepare("select price from quotes where symbol='FIXD'").get().price).toBe(11);
  });
  it("ingest_write refuses a wrong key, private tables, bad rows, and a stopped day", async () => {
    expect((await ingest({ table: "quotes", rows: [quote] }, "wrong-key-wrong-key")).status).toBe(401);
    expect((await call(v2.ingestWrite, "", { method: "POST", person: "owner", body: { table: "quotes", rows: [quote] } })).status).toBe(401); // a signed-in browser is not the ingest key
    for (const table of ["calls", "jobs", "changes", "news_rank", "write_budget"]) expect((await ingest({ table, rows: [{}] })).status).toBe(400);
    expect((await ingest({ table: "quotes", rows: [{ ...quote, bogus: 1 }] })).status).toBe(400);
    expect((await ingest({ table: "quotes", rows: [{ symbol: "FIXD" }] })).status).toBe(400);
    expect((await ingest({ table: "quotes", rows: [] })).status).toBe(400);
    env.DB.db.prepare("update write_budget set writes=85000 where day='2026-11-25'").run();
    const stopped = await ingest({ table: "quotes", rows: [quote] });
    expect(stopped.status).toBe(429); ok("ingest_write", stopped.body);
    expect(stopped.body).toMatchObject({ written: 0, stopped: true });
    expect(env.DB.db.prepare("select count(*) n from quotes where symbol='FIXD'").get().n).toBe(0);
  });
  it("ingest_write is not usable without a configured key", async () => {
    env.SP_INGEST_KEY = undefined;
    expect((await ingest({ table: "quotes", rows: [quote] }, "undefined")).status).toBe(401);
  });
});

describe("middleware", () => {
  const run = (path, { method = "GET", headers = {}, cookie } = {}) => {
    let passed = false;
    return middleware({ request: new Request(O + path, { method, headers }), env, data: {}, next: async () => { passed = true; return new Response("{}"); } })
      .then((res) => ({ status: res.status, passed }));
  };
  it("the ingest door opens only for the ingest key, with no cookie needed", async () => {
    expect(await run("/api/v2/ingest", { method: "POST", headers: { "X-SP-Ingest-Key": "ingest-key-0123456789" } })).toMatchObject({ passed: true });
    expect(await run("/api/v2/ingest", { method: "POST", headers: { "X-SP-Ingest-Key": "nope" } })).toMatchObject({ status: 401, passed: false });
    expect(await run("/api/v2/ingest", { method: "POST" })).toMatchObject({ status: 401, passed: false });
  });
  it("every other v2 route still needs a signed-in person", async () => {
    expect(await run("/api/v2/jobs")).toMatchObject({ status: 401, passed: false });
  });
});

it("every route in the contract has a handler and a test above", () => {
  const names = { jobs_create: "jobsCreate", jobs_get: "jobsGet", jobs_list: "jobsList", jobs_rerun: "jobsRerun", changes_list: "changesList", changes_seen: "changesSeen", call_get: "callGet", lists_get: "listsGet", quotes_get: "quotesGet", news_list: "newsList", og_image: "ogImage", feedback_create: "feedbackCreate", feedback_list: "feedbackList", ask_not_meant: "askNotMeant", ask_decide: "askDecide", budget_get: "budgetGet", ingest_write: "ingestWrite" };
  expect(CONTRACT.routes.map((r) => r.id).sort()).toEqual(Object.keys(names).sort());
  for (const fn of Object.values(names)) expect(typeof v2[fn]).toBe("function");
});

describe("quotes_get refresh on open (T15)", () => {
  const sec = Math.floor(NOW.getTime() / 1000) - 30;
  const yahoo = async () => ({ ok: true, status: 200, json: async () => ({ chart: { result: [{ meta: { regularMarketPrice: 321, chartPreviousClose: 300, regularMarketTime: sec } }] } }), headers: { getSetCookie: () => [] } });
  const stale = () => env.DB.db.prepare("update quotes set as_of = '2026-11-25T09:20:00+05:30' where symbol = 'FIXB'").run();

  it("refetches a quote older than 5 minutes while the market is open, and answers with the fresh one", async () => {
    stale();
    const r = await call(v2.quotesGet, "/api/v2/quotes?symbols=FIXB&refresh=1", { extra: { fetch: yahoo, sleep: async () => {} } });
    ok("quotes_get", r.body);
    expect(r.body.quotes[0]).toMatchObject({ symbol: "FIXB", price: 321, age_seconds: 30 });
  });
  it("does not fetch when refresh is not asked, the quote is fresh, or the market is shut", async () => {
    let n = 0; const f = async (...a) => { n++; return yahoo(...a); };
    stale(); await call(v2.quotesGet, "/api/v2/quotes?symbols=FIXB", { extra: { fetch: f } });
    env.DB.db.prepare("update quotes set as_of = '2026-11-25T09:58:00+05:30' where symbol = 'FIXB'").run();
    await call(v2.quotesGet, "/api/v2/quotes?symbols=FIXB&refresh=1", { extra: { fetch: f, sleep: async () => {} } });
    stale();
    const shut = new Date("2026-11-25T20:00:00+05:30");
    await call(v2.quotesGet, "/api/v2/quotes?symbols=FIXB&refresh=1", { extra: { fetch: f, sleep: async () => {}, now: shut } });
    expect(n).toBe(0);
  });
  it("refreshes at most 3 symbols per open and a person must be signed in", async () => {
    const urls = []; const f = async (u) => { urls.push(u); return yahoo(); };
    await call(v2.quotesGet, "/api/v2/quotes?symbols=A1,A2,A3,A4,A5&refresh=1", { extra: { fetch: f, sleep: async () => {} } });
    expect(urls.length).toBeLessThanOrEqual(3);
    expect((await call(v2.quotesGet, "/api/v2/quotes?symbols=A1&refresh=1", { person: null, extra: { fetch: f } })).status).toBe(401);
  });
});
