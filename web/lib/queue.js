// The request queue in KV. Keys q:<id>, ids sort by time, so `list` returns them oldest first.
// schemas/queue-kinds.json lists every kind with its payload keys; the VM reads the same file.
import spec from "../../schemas/queue-kinds.json";
export const KINDS = Object.keys(spec.kinds);
export const PAYLOAD_KEYS = spec.kinds;
const PENDING_TTL = 30 * 24 * 3600;
const DONE_TTL = 7 * 24 * 3600;
const key = (id) => `q:${id}`;

export const newId = (now = Date.now()) =>
  `${String(now).padStart(14, "0")}-${[...crypto.getRandomValues(new Uint8Array(3))].map((b) => b.toString(16).padStart(2, "0")).join("")}`;

export async function listAll(env) {
  const items = [];
  let cursor;
  do {
    const page = await env.SP.list({ prefix: "q:", cursor });
    const got = await Promise.all(page.keys.map((k) => env.SP.get(k.name, "json")));
    items.push(...got.filter(Boolean));
    cursor = page.list_complete ? undefined : page.cursor;
  } while (cursor);
  return items.sort((a, b) => (a.id < b.id ? -1 : 1));
}

export async function add(env, kind, payload, by) {
  const item = { id: newId(), kind, payload, by, at: new Date().toISOString(), taken_at: null, status: "pending", note: "" };
  await env.SP.put(key(item.id), JSON.stringify(item), { expirationTtl: PENDING_TTL });
  return item;
}

export const get = (env, id) => env.SP.get(key(id), "json");
export const remove = (env, id) => env.SP.delete(key(id));

export async function markTaken(env, item) {
  if (item.taken_at) return item;
  item = { ...item, taken_at: new Date().toISOString(), status: "taken" };
  await env.SP.put(key(item.id), JSON.stringify(item), { expirationTtl: PENDING_TTL });
  return item;
}

export async function finish(env, item, status, note) {
  item = { ...item, taken_at: item.taken_at || new Date().toISOString(), status, note };
  await env.SP.put(key(item.id), JSON.stringify(item), { expirationTtl: DONE_TTL });
  return item;
}

// Lane W: rules a request must pass before it is queued. Returns null, or {status, error}.
export const ASK_ANALYST_PER_DAY = 5;
const IST_MS = 5.5 * 3600 * 1000;
const istParts = (ms) => {
  const d = new Date(ms + IST_MS);
  return { day: d.toISOString().slice(0, 10), hour: d.getUTCHours() };
};
const SYMBOL = /^[A-Z0-9&-]{1,20}$/i;

export async function guard(env, kind, payload, now = Date.now()) {
  if (kind === "long_term_mark") {
    if (typeof payload?.symbol !== "string" || !SYMBOL.test(payload.symbol.trim())) return { status: 400, error: "Which stock?" };
    if (typeof payload.on !== "boolean") return { status: 400, error: "Say whether to mark it or unmark it." };
  }
  if (kind === "ask_analyst") {
    if (typeof payload?.symbol !== "string" || !SYMBOL.test(payload.symbol.trim())) return { status: 400, error: "Which stock?" };
    const here = istParts(now);
    // 19:00 to 22:00 IST is the nightly run; the analyst's budget belongs to it.
    if (here.hour >= 19 && here.hour < 22) return { status: 429, error: "The analyst is busy with tonight's run until 22:00. Ask again after 10 pm, or tomorrow." };
    const today = (await listAll(env)).filter((i) => i.kind === "ask_analyst" && istParts(Date.parse(i.at)).day === here.day);
    if (today.length >= ASK_ANALYST_PER_DAY) return { status: 429, error: `Only ${ASK_ANALYST_PER_DAY} questions to the analyst a day. Try again tomorrow.` };
  }
  return null;
}
