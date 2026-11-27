// v2 live API (ticket T13). One handler per route in schemas/live-contract.json; the files under
// functions/api/v2/ only wire them to URLs. Handlers take a Pages Functions context and return a Response.
// Optional context.now (Date) and context.fetch exist so tests control the clock and the network.
import { json, readJson } from "../http.js";
import { knownPerson, people, ingestAllowed } from "../auth.js";
import contract from "../../../schemas/live-contract.json";
import { marketOpen, refreshQuotes } from "./quotes.js";

const IST_MS = 5.5 * 3600 * 1000;
const istISO = (d) => new Date(d.getTime() + IST_MS).toISOString().replace(/\.\d+Z$/, "+05:30");
const istDay = (d) => new Date(d.getTime() + IST_MS).toISOString().slice(0, 10);
const nowOf = (ctx) => (ctx.now instanceof Date ? ctx.now : new Date());
const rid = (prefix, d) => `${prefix}_${d.getTime().toString(36)}${[...crypto.getRandomValues(new Uint8Array(4))].map((b) => b.toString(16).padStart(2, "0")).join("")}`;
const SEVEN_DAYS_MS = 7 * 24 * 3600 * 1000;

// Who is calling: "owner", "father" (any other signed-in person) or null. people() already maps a legacy
// SP_OWNER id to "owner"; SP_OWNER only decides when SP_PEOPLE has no "owner" key (and then never beats it).
export function roleOf(env, id) {
  if (!id || !knownPerson(env, id)) return null;
  const hasOwnerKey = Object.hasOwn(people(env), "owner");
  return id === (hasOwnerKey ? "owner" : env.SP_OWNER || "owner") ? "owner" : "father";
}
const needPerson = (ctx) => { const role = roleOf(ctx.env, ctx.data?.person); return role ? { role } : { fail: json({ error: "login_needed" }, 401) }; };
const needOwner = (ctx) => {
  const { role, fail } = needPerson(ctx);
  if (fail) return { fail };
  return role === "owner" ? { role } : { fail: json({ error: "owner_only" }, 403) };
};
const bool = (v) => v === 1 || v === true;
const parse = (text) => { try { return JSON.parse(text); } catch { return null; } };
const param = (ctx, name) => decodeURIComponent(String(ctx.params?.[name] ?? ""));
const q = (ctx) => new URL(ctx.request.url).searchParams;
const clamp = (raw, def, max) => { const n = Number.parseInt(raw ?? "", 10); return Number.isFinite(n) && n > 0 ? Math.min(n, max) : def; };

const jobOut = (r) => ({ ...r, payload: parse(r.payload) ?? {} });
const changeOut = (r) => r;

// ---- jobs ----
async function insertJob(db, kind, payload, askedBy, now) {
  const id = rid("job", now);
  await db.prepare("insert into jobs (id, kind, payload, asked_by, status, created_at) values (?, ?, ?, ?, 'queued', ?)")
    .bind(id, kind, JSON.stringify(payload), askedBy, istISO(now)).run();
  return id;
}

// The Kite callback's job: the owner just logged in, so the VM reads holdings and the page follows the lines.
export const addSyncJob = (db, now = new Date()) => insertJob(db, "sync", {}, "owner", now);

export async function jobsCreate(ctx) {
  const { role, fail } = needPerson(ctx); if (fail) return fail;
  const body = await readJson(ctx.request);
  const spec = body && Object.hasOwn(contract.job_kinds, body.kind) ? contract.job_kinds[body.kind] : null;
  if (!spec) return json({ error: "unknown_kind" }, 400);
  const payload = body.payload ?? {};
  if (typeof payload !== "object" || payload === null || Array.isArray(payload)) return json({ error: "payload_must_be_object" }, 400);
  const keys = Object.keys(payload);
  if (keys.some((k) => !spec.payload.includes(k)) || spec.payload.some((k) => !(k in payload))) return json({ error: "payload_keys", want: spec.payload }, 400);
  return json({ id: await insertJob(ctx.env.DB, body.kind, payload, role, nowOf(ctx)), status: "queued" });
}

export async function jobsGet(ctx) {
  const { fail } = needPerson(ctx); if (fail) return fail;
  const id = param(ctx, "id");
  const job = await ctx.env.DB.prepare("select * from jobs where id = ?").bind(id).first();
  if (!job) return json({ error: "not_found" }, 404);
  const { results } = await ctx.env.DB.prepare("select * from job_lines where job_id = ? order by seq").bind(id).all();
  return json({ job: jobOut(job), lines: results });
}

export async function jobsList(ctx) {
  const { fail } = needOwner(ctx); if (fail) return fail;
  const status = q(ctx).get("status");
  const limit = clamp(q(ctx).get("limit"), 50, 200);
  const sql = `select * from jobs ${status ? "where status = ?" : ""} order by created_at desc, id desc limit ?`;
  const stmt = ctx.env.DB.prepare(sql);
  const { results } = await (status ? stmt.bind(status, limit) : stmt.bind(limit)).all();
  return json({ jobs: results.map(jobOut) });
}

export async function jobsRerun(ctx) {
  const { fail } = needOwner(ctx); if (fail) return fail;
  const job = await ctx.env.DB.prepare("select * from jobs where id = ?").bind(param(ctx, "id")).first();
  if (!job) return json({ error: "not_found" }, 404);
  if (job.status !== "failed") return json({ error: "only_failed_jobs_rerun" }, 409);
  return json({ id: await insertJob(ctx.env.DB, job.kind, parse(job.payload) ?? {}, "owner", nowOf(ctx)), status: "queued" });
}

// ---- marks ----
export async function changesList(ctx) {
  const { role, fail } = needPerson(ctx); if (fail) return fail;
  const now = nowOf(ctx);
  const since = q(ctx).get("since");
  const floor = istISO(new Date(now.getTime() - SEVEN_DAYS_MS));
  const { results } = await ctx.env.DB.prepare("select * from changes where person = ? and at >= ? and at >= ? order by at desc, id desc")
    .bind(role, floor, since || "").all();
  return json({ person: role, unseen_count: results.filter((c) => !c.seen_at).length, items: results.map(changeOut) });
}

export async function changesSeen(ctx) {
  const { role, fail } = needPerson(ctx); if (fail) return fail;
  const body = (await readJson(ctx.request)) ?? {};
  const at = istISO(nowOf(ctx));
  const db = ctx.env.DB;
  let stmt;
  if (body.all === true) stmt = db.prepare("update changes set seen_at = ? where person = ? and seen_at is null").bind(at, role);
  else if (typeof body.symbol === "string" && body.symbol) stmt = db.prepare("update changes set seen_at = ? where person = ? and symbol = ? and seen_at is null").bind(at, role, body.symbol);
  else if (Array.isArray(body.ids) && body.ids.length && body.ids.length <= 200 && body.ids.every((i) => typeof i === "string")) {
    stmt = db.prepare(`update changes set seen_at = ? where person = ? and seen_at is null and id in (${body.ids.map(() => "?").join(",")})`).bind(at, role, ...body.ids);
  } else return json({ error: "say_symbol_ids_or_all" }, 400);
  return json({ marked: (await stmt.run()).meta.changes });
}

// ---- stocks ----
const callOut = ({ out_of_date, news_buy, form, ...rest }) => ({ ...rest, form: parse(form), out_of_date: bool(out_of_date), news_buy: bool(news_buy) });

export async function callGet(ctx) {
  const { role, fail } = needPerson(ctx); if (fail) return fail;
  const symbol = param(ctx, "symbol");
  const exchange = q(ctx).get("exchange");
  const row = await ctx.env.DB.prepare(`select * from calls where symbol = ? ${exchange ? "and exchange = ?" : ""} order by exchange desc limit 1`)
    .bind(...(exchange ? [symbol, exchange] : [symbol])).first(); // NSE sorts after BSE, so desc prefers NSE
  if (!row) return json({ error: "not_found" }, 404);
  const { results } = await ctx.env.DB.prepare("select * from changes where person = ? and symbol = ? order by at desc, id desc").bind(role, symbol).all();
  return json({ call: callOut(row), changes: results.map(changeOut) });
}

export async function listsGet(ctx) {
  const { fail } = needPerson(ctx); if (fail) return fail;
  const { results } = await ctx.env.DB.prepare(
    `select l.symbol, l.exchange, l.rank, l.reason, l.reason_bn, l.since, c.call, c.chance_3m, c.out_of_date
     from lists l left join calls c on c.symbol = l.symbol and c.exchange = l.exchange
     where l.list_name = ? order by l.rank, l.symbol`).bind(param(ctx, "name")).all();
  const items = results.map(({ out_of_date, call, chance_3m, ...r }) => ({ ...r, call: call ?? null, chance_3m: chance_3m ?? null, out_of_date: bool(out_of_date) }));
  return json({ list_name: param(ctx, "name"), items });
}

// T29: the private screens (Holdings, Tax, records) read one stored document each. Names are fixed by the contract.
export async function viewsGet(ctx) {
  const { fail } = needPerson(ctx); if (fail) return fail;
  const name = param(ctx, "name");
  if (!contract.tables.views.columns.name.slice(5, -1).split("|").includes(name)) return json({ error: "not_found" }, 404);
  const row = await ctx.env.DB.prepare("select name, doc, as_of, written_at from views where name = ?").bind(name).first();
  if (!row) return json({ error: "not_found" }, 404);
  return json({ ...row, doc: parse(row.doc) ?? {} });
}

export async function quotesGet(ctx) {
  const { fail } = needPerson(ctx); if (fail) return fail;
  const symbols = [...new Set((q(ctx).get("symbols") || "").split(",").map((s) => s.trim()).filter(Boolean))].slice(0, 100);
  if (!symbols.length) return json({ quotes: [] });
  const db = ctx.env.DB, date = nowOf(ctx);
  const read = () => db.prepare(`select * from quotes where symbol in (${symbols.map(() => "?").join(",")}) order by symbol, exchange`).bind(...symbols).all();
  let { results } = await read();
  // T15: opening a stock asks for refresh=1. Quotes older than 5 minutes are refetched while the market is open,
  // at most 3 stocks per call and never one fetched in the last minute. The page shows the stored price and its age
  // first, then swaps in the new one; if the source fails the old row is simply returned.
  if (q(ctx).get("refresh") === "1" && marketOpen(date)) {
    const age = (r) => (date.getTime() - Date.parse(r.as_of)) / 1000;
    const known = new Map(results.map((r) => [r.symbol, r]));
    const todo = symbols.filter((s) => !known.has(s) || age(known.get(s)) > 300).slice(0, 3)
      .map((s) => ({ symbol: s, exchange: known.get(s)?.exchange ?? "NSE" }));
    if (todo.length) {
      try { await refreshQuotes({ db, symbols: todo, fetch: ctx.fetch ?? fetch, now: date, sleep: ctx.sleep, minAgeSeconds: 60 }); ({ results } = await read()); } catch { /* keep the stored rows */ }
    }
  }
  const now = date.getTime();
  return json({ quotes: results.map((r) => ({ ...r, age_seconds: Math.max(0, Math.floor((now - Date.parse(r.as_of)) / 1000)) })) });
}

// ---- news ----
export async function newsList(ctx) {
  const { fail } = needPerson(ctx); if (fail) return fail;
  const limit = clamp(q(ctx).get("limit"), 30, 100);
  const db = ctx.env.DB;
  const { results: rows } = await db.prepare(
    `select i.*, r.closeness, r.score, r.tier, r.ranked_at from news_items i left join news_rank r on r.item_id = i.id
     order by coalesce(r.score, 0) desc, i.published_at desc limit ?`).bind(limit).all();
  const ids = rows.map((r) => r.id);
  const tags = ids.length ? (await db.prepare(`select * from news_tags where item_id in (${ids.map(() => "?").join(",")}) order by symbol`).bind(...ids).all()).results : [];
  const items = rows.map(({ closeness, score, tier, ranked_at, market_wide, ...i }) => ({
    ...i, market_wide: bool(market_wide),
    tags: tags.filter((t) => t.item_id === i.id).map((t) => ({ ...t, changes_call: bool(t.changes_call) })),
    // News nobody has ranked yet still shows, as low.
    rank: { item_id: i.id, closeness: closeness ?? "other", score: score ?? 0, tier: tier ?? "low", ranked_at: ranked_at ?? i.published_at },
  }));
  const bySector = new Map();
  for (const i of items) if (i.sector) bySector.set(i.sector, [...(bySector.get(i.sector) ?? []), i.direction]);
  const sector_mood = [...bySector].map(([sector, dirs]) => {
    const good = dirs.filter((d) => d === "good").length, bad = dirs.filter((d) => d === "bad").length;
    return { sector, mood: good > bad ? "good" : bad > good ? "bad" : "mixed", items: dirs.length };
  }).sort((a, b) => b.items - a.items || a.sector.localeCompare(b.sector));
  return json({ items, sector_mood });
}

const PRIVATE_HOST = /^(localhost|.*\.local|.*\.internal|0\.0\.0\.0|127\..*|10\..*|192\.168\..*|169\.254\..*|172\.(1[6-9]|2\d|3[01])\..*|\[.*\]|\d+)$/i;
// One linear pass over the head: collects the tags we need, never backtracks (a page full of
// unclosed tags must not cost more CPU than a clean one).
const attr = (tag, name) => {
  const m = new RegExp(`\\s${name}\\s*=\\s*(?:"([^"]*)"|'([^']*)')`, "i").exec(tag);
  return m ? (m[1] ?? m[2]) : null;
};
function headTags(html) {
  const meta = {}; let icon = null, pos = 0, seen = 0;
  const low = html.toLowerCase();
  while (seen++ < 400) {
    const at = low.indexOf("<", pos);
    if (at < 0) break;
    const kind = low.startsWith("<meta", at) ? "meta" : low.startsWith("<link", at) ? "link" : null;
    const end = low.indexOf(">", at);
    if (end < 0) break;
    pos = kind ? end + 1 : at + 1;
    if (!kind) continue;
    const tag = html.slice(at, end + 1);
    if (kind === "meta") {
      const key = (attr(tag, "property") ?? attr(tag, "name") ?? "").toLowerCase();
      if ((key === "og:image" || key === "twitter:image") && meta[key] === undefined) meta[key] = attr(tag, "content");
    } else if (icon === null && /icon/i.test(attr(tag, "rel") ?? "")) icon = attr(tag, "href");
  }
  return { image: meta["og:image"] ?? meta["twitter:image"] ?? null, icon };
}
const absolute = (href, base) => { if (!href) return null; try { const u = new URL(href, base); return u.protocol === "https:" || u.protocol === "http:" ? u.href : null; } catch { return null; } };

const OG_READ_LIMIT = 102_400; // contract: read_limit_bytes (probe T2)
const OG_DAY = 86_400, OG_WEEK = 7 * OG_DAY;
const publicUrl = (raw) => {
  try { const u = new URL(raw); return /^https?:$/.test(u.protocol) && !PRIVATE_HOST.test(u.hostname) ? u : null; } catch { return null; }
};

// Reads the start of the page only: stops at the end of <head> or after 100 KB, whichever comes first.
async function readHead(res) {
  if (!res.body) return "";
  const reader = res.body.getReader(), dec = new TextDecoder();
  let html = "", bytes = 0, from = 0;
  try {
    while (bytes < OG_READ_LIMIT) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.length;
      html += dec.decode(value, { stream: true });
      const end = html.toLowerCase().indexOf("</head", Math.max(0, from - 6));
      if (end >= 0) { html = html.slice(0, end); break; }
      from = html.length;
    }
  } finally { await reader.cancel().catch(() => {}); }
  return html.slice(0, OG_READ_LIMIT);
}

// Follows up to 3 redirects, checking every hop is a public address.
async function fetchPage(fetcher, start) {
  let url = start;
  for (let hop = 0; hop < 4; hop++) {
    const res = await fetcher(url.href, { headers: { "User-Agent": "stockpilot-card/1.0", Accept: "text/html" }, redirect: "manual" });
    if (res.status >= 300 && res.status < 400) {
      const next = publicUrl(new URL(res.headers.get("Location") || "", url).href);
      if (!next) return null;
      url = next; continue;
    }
    return res.ok ? { res, url } : null;
  }
  return null;
}

const ogReply = (body, maxAge) => new Response(JSON.stringify(body), { headers: { "Content-Type": "application/json", "Cache-Control": `public, max-age=${maxAge}` } });

export async function ogImage(ctx) {
  const { fail } = needPerson(ctx); if (fail) return fail;
  const target = publicUrl(q(ctx).get("url") || "");
  if (!target) return json({ error: "bad_url" }, 400);
  target.hash = "";
  const site = publicUrl(q(ctx).get("site") || "");
  const cache = ctx.cache ?? globalThis.caches?.default;
  const key = new Request(new URL(ctx.request.url).origin + "/api/v2/og?url=" + encodeURIComponent(target.href) + (site ? "&site=" + encodeURIComponent(site.origin) : ""));
  const hit = await cache?.match(key).catch(() => null);
  if (hit) return hit;
  const keep = async (res) => { await cache?.put(key, res.clone()).catch(() => {}); return res; };
  const empty = () => ogReply({ image: null, logo: null }, 3600); // a failed read is retried within the hour

  // Google News links open a redirect page, not the article: its image is Google's, not the publisher's.
  if (target.hostname === "news.google.com") {
    return keep(ogReply({ image: null, logo: site ? new URL("/favicon.ico", site.origin).href : null }, OG_WEEK));
  }
  try {
    const page = await fetchPage(ctx.fetch ?? fetch, target);
    if (!page) return empty();
    const html = await readHead(page.res);
    const { image, icon } = headTags(html);
    return keep(ogReply({ image: absolute(image, page.url), logo: absolute(icon, page.url) }, OG_WEEK));
  } catch { return empty(); }
}

// ---- feedback and asks ----
export async function feedbackCreate(ctx) {
  const { role, fail } = needPerson(ctx); if (fail) return fail;
  const body = await readJson(ctx.request);
  const text = typeof body?.text === "string" ? body.text.trim() : "";
  if (!text || text.length > 4000) return json({ error: "text_needed" }, 400);
  const now = nowOf(ctx), id = rid("fb", now);
  await ctx.env.DB.batch([
    ctx.env.DB.prepare("insert into feedback (id, person, text, status, created_at) values (?, ?, ?, 'received', ?)").bind(id, role, text, istISO(now)),
    ctx.env.DB.prepare("insert into jobs (id, kind, payload, asked_by, status, created_at) values (?, 'feedback_read', ?, ?, 'queued', ?)")
      .bind(rid("job", now), JSON.stringify({ feedback_id: id }), role, istISO(now)),
  ]);
  return json({ id, status: "received" });
}

export async function feedbackList(ctx) {
  const { role, fail } = needPerson(ctx); if (fail) return fail;
  const db = ctx.env.DB;
  const { results: items } = await db.prepare("select * from feedback where person = ? order by created_at desc, id desc limit 100").bind(role).all();
  const ids = items.map((f) => f.id);
  const asks = ids.length ? (await db.prepare(`select * from asks where feedback_id in (${ids.map(() => "?").join(",")}) order by updated_at, id`).bind(...ids).all()).results : [];
  return json({ items: items.map((f) => ({ id: f.id, person: f.person, text: f.text, status: f.status, created_at: f.created_at,
    asks: asks.filter((a) => a.feedback_id === f.id).map((a) => ({ ...a, not_meant: bool(a.not_meant) })) })) });
}

export async function askNotMeant(ctx) {
  const { role, fail } = needPerson(ctx); if (fail) return fail;
  const id = param(ctx, "id");
  const r = await ctx.env.DB.prepare("update asks set not_meant = 1, updated_at = ? where id = ? and feedback_id in (select id from feedback where person = ?)")
    .bind(istISO(nowOf(ctx)), id, role).run();
  return r.meta.changes ? json({ id, not_meant: true }) : json({ error: "not_found" }, 404);
}

export async function askDecide(ctx) {
  const { fail } = needOwner(ctx); if (fail) return fail;
  const body = await readJson(ctx.request);
  if (body?.decision !== "approve" && body?.decision !== "decline") return json({ error: "approve_or_decline" }, 400);
  const db = ctx.env.DB, id = param(ctx, "id"), now = nowOf(ctx);
  const ask = await db.prepare("select a.*, f.person as author from asks a join feedback f on f.id = a.feedback_id where a.id = ?").bind(id).first();
  if (!ask) return json({ error: "not_found" }, 404);
  if (ask.status !== "waiting_for_approval") return json({ error: "not_waiting_for_approval" }, 409);
  const status = body.decision === "approve" ? "being_built" : "declined";
  await db.batch([
    db.prepare("update asks set status = ?, updated_at = ? where id = ? and status = 'waiting_for_approval'").bind(status, istISO(now), id),
    // The author sees a yellow mark: "a feedback ask changed status".
    db.prepare("insert into changes (id, person, symbol, kind, old_value, new_value, reason, at) values (?, ?, 'feedback', 'ask_status', 'waiting_for_approval', ?, ?, ?)")
      .bind(rid("chg", now), ask.author, status, `${ask.line_en}: ${status === "being_built" ? "approved, being built" : "declined"}`, istISO(now)),
  ]);
  return json({ id, status });
}

// ---- operations ----
const budgetOf = async (db, day) => (await db.prepare("select * from write_budget where day = ?").bind(day).first())
  ?? { day, writes: 0, warn_at: contract.write_budget.warn_at, stop_at: contract.write_budget.stop_at };
const budgetStatus = (b) => (b.writes >= b.stop_at ? "stopped" : b.writes >= b.warn_at ? "warn" : "ok");

export async function budgetGet(ctx) {
  const { fail } = needOwner(ctx); if (fail) return fail;
  const b = await budgetOf(ctx.env.DB, istDay(nowOf(ctx)));
  return json({ day: b.day, writes: b.writes, warn_at: b.warn_at, stop_at: b.stop_at, status: budgetStatus(b) });
}

const MAX_INGEST_ROWS = 200;
export async function ingestWrite(ctx) {
  if (!(await ingestAllowed(ctx.request, ctx.env))) return json({ error: "bad_ingest_key" }, 401);
  const body = await readJson(ctx.request);
  const table = body?.table, spec = Object.hasOwn(contract.tables, table ?? "") ? contract.tables[table] : null;
  if (!spec || spec.writer !== "ingest") return json({ error: "table_not_open" }, 400);
  const rows = body.rows;
  if (!Array.isArray(rows) || !rows.length || rows.length > MAX_INGEST_ROWS) return json({ error: "rows_1_to_200" }, 400);
  const cols = Object.keys(spec.columns), required = cols.filter((c) => !spec.columns[c].endsWith("?"));
  for (const r of rows) {
    if (!r || typeof r !== "object" || Array.isArray(r)) return json({ error: "bad_row" }, 400);
    if (Object.keys(r).some((k) => !cols.includes(k)) || required.some((k) => r[k] === undefined || r[k] === null)) return json({ error: "bad_row", columns: cols }, 400);
  }
  const db = ctx.env.DB, now = nowOf(ctx), day = istDay(now);
  const budget = await budgetOf(db, day);
  if (budget.writes >= budget.stop_at) return json({ written: 0, writes_today: budget.writes, stopped: true }, 429);
  const cost = rows.length * (1 + spec.indexes.length);
  const sql = `insert or replace into ${table} (${cols.join(",")}) values (${cols.map(() => "?").join(",")})`;
  const val = (v) => (v === undefined ? null : typeof v === "boolean" ? Number(v) : typeof v === "object" && v !== null ? JSON.stringify(v) : v);
  await db.batch([
    ...rows.map((r) => db.prepare(sql).bind(...cols.map((c) => val(r[c])))),
    db.prepare("insert into write_budget (day, writes, warn_at, stop_at, updated_at) values (?, ?, ?, ?, ?) on conflict(day) do update set writes = writes + excluded.writes, updated_at = excluded.updated_at")
      .bind(day, cost, budget.warn_at, budget.stop_at, istISO(now)),
  ]);
  const writes = budget.writes + cost;
  return json({ written: rows.length, writes_today: writes, stopped: writes >= budget.stop_at });
}
